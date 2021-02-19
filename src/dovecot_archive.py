import argparse
import datetime
import dateutil.relativedelta
import logging
import os
import re
import subprocess

__version__ = '1.0.1'
__usage__ = '''
dovecot-archive is a doveadm wrapper for common mail archival tasks.

Scenario 1) I have way too many mails and it makes my e-mail client slow. I want to move sent
            and received mails older than 3 years to a different user/account (which I only open
            in my e-mail client when I really need to), and I want to retain the same folder
            structure of the mailboxes as I have under the current user/account.
            I don't want to archive thrash, spam, etc.

    Create a weekly cron task:
    dovecot-archive --user original.user@example.com --dst-user archival.user@example.com \\
                    --folder INBOX --folder Sent --before "3 years"

Scenario 2) I have way too many mails and I want to move mails older than 14 days into an archive
            folder under the same user/account. I also want to create a subfolder for every year.

    Create a daily cron task:
    dovecot-archive --user user@example.com --folder INBOX --dst-root-folder Archive \\
                    --split-by-year --before "14 days"

Scenario 3) An employee is leaving the company and I want to move all their mail to a new
            user/account of the employee replacing them. I want to move the whole folder
            structure, but to place it under a subfolder so it doesn't interfere with the new
            empolyee's mails.

    Manually run once:
    dovecot-archive --user leaver@example.com --dst-user joiner@example.com --dst-root-folder "Jane Doe"
'''

logger = logging.getLogger('dovecot-archive')

def run(cmd, **kwargs):
    '''
    Runs a command suppressing its output unless overridden.

    :param cmd: The command to run as a list of the binary and the parameters.
    :type cmd: list

    :key kwargs: Keyword args for subprocess.run

    :return: Completed process.
    :rtype: subprocess.CompletedProcess
    '''
    logger.debug(cmd)
    subprocess_args = {'stdout': subprocess.DEVNULL,
                       'stderr': subprocess.DEVNULL,
                       'check': True}
    subprocess_args.update(kwargs)
    return subprocess.run(cmd, **subprocess_args) # pylint: disable=subprocess-run-check


def move_mails(user, folder, dst_user, dst_folder, since, before, copy):
    '''
    Moves or copies the mails matching the given criteria.

    :param user: The source user.
    :type user: str

    :param folder: The source folder under the source user.
    :type folder: str

    :param dst_user: The destination user, can be the same as source.
    :type dst_user: str

    :param dst_folder: The destination folder under the destination user.
    :type dst_folder: str

    :param since: The earliest (least recent) internal date of the mails to be moved/copied.
                  The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                  or unix timestamp. `None` means unbounded selection.
    :type since: str

    :param before: The latest (most recent) internal date of the mails to be moved/copied.
                   The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                   or unix timestamp. `None` means unbounded selection.
    :type before: str

    :param copy: Flag designating if the mails should be moved (expunged from the source folder)
                 or copied (remain also in the source folder). `False` = move, `True` = copy
    :type copy: bool

    :return: Nothing.
    :rtype: None
    '''
    logger.info('%s mails sent between %s and %s from user %s folder %s to user %s folder %s',
                'Copying' if copy else 'Moving', since if since else 'the beginning of time',
                before if before else 'now', user, folder, dst_user, dst_folder)
    cmd = ['doveadm', 'copy' if copy else 'move', '-u', dst_user, dst_folder]
    if user != dst_user:
        cmd.extend(('user', user))
    cmd.extend(('mailbox', folder))
    if since:
        cmd.extend(('since', since))
    if before:
        cmd.extend(('before', before))
    if not since and not before:
        cmd.append('all')
    run(cmd)


def folder_exists(user, folder):
    '''
    Checks if a folder exists.

    :param user: User under which the folder is checked to exist.
    :type user: str

    :param folder: The folder which is checked to exist under the user.
    :type folder: str

    :return: `True` if the folder exists, otherwise `False`.
    :rtype: bool
    '''
    logger.info('Checking if user %s folder %s exists', user, folder)
    try:
        run(['doveadm', 'mailbox', 'status', '-u', user, 'messages', folder])
        return True
    except subprocess.CalledProcessError:
        return False


def create_folder(user, folder):
    '''
    Creates a folder and subscribes the user to it.

    :param user: User under which the folder will be created.
    :type user: str

    :param folder: The folder which will be created under the user.
    :type folder: str

    :return: Nothing.
    :rtype: None
    '''
    logger.info('Creating folder %s and subscribing user %s to is', folder, user)
    run(['doveadm', 'mailbox', 'create', '-u', user, folder])
    run(['doveadm', 'mailbox', 'subscribe', '-u', user, folder])


def folder_has_mails_to_process(user, folder, since, before):
    '''
    Checks if there are any mails matching the given criteria to be processed.

    :param user: Source user under which the mails are checked.
    :type user: str

    :param folder: The folder under the source user in which the mails are checked.
    :type folder: str

    :param since: The earliest (least recent) internal date of the mails to be moved/copied.
                  The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                  or unix timestamp. `None` means unbounded selection.
    :type since: str

    :param before: The latest (most recent) internal date of the mails to be moved/copied.
                   The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                   or unix timestamp. `None` means unbounded selection.
    :type before: str

    :return: `True` is there are any mails matching the criteria, `False` otherwise.
    :rtype: bool
    '''
    logger.info('Checking if user %s folder %s has any mails sent between %s and %s',
                user, folder, since if since else 'the beginning of time',
                before if before else 'now')
    cmd = ['doveadm', 'search', '-u', user, 'mailbox', folder]
    if since:
        cmd.extend(('since', since))
    if before:
        cmd.extend(('before', before))
    if not since and not before:
        cmd.append('all')
    return bool(run(cmd, stdout=subprocess.PIPE).stdout)


def get_subfolders(user, folder):
    '''
    Compiles a list of all subfolder for the given folder.
    The list contains also the folder itself.

    :param user: Source user under which the folders are checked.
    :type user: str

    :param folder: The folder under the source user in which the subfolders are checked.
    :type folder: str

    :return: list of all subfolders for the given folder.
             The list contains also the folder itself.
    :rtype: list
    '''
    logger.info('Getting all subfolders for user %s folder %s', user, folder)
    cmd = ['doveadm', 'mailbox', 'list', '-u', user, f'{folder}*']
    p = run(cmd, stdout=subprocess.PIPE)
    return p.stdout.decode().splitlines()


def process_folder(user, folder, dst_user, dst_folder, since, before, copy):
    '''
    Checks if there are any mails to be processed for the given criteria
    and processes them, if there are any.

    :param user: The source user.
    :type user: str

    :param folder: The source folder under the source user.
    :type folder: str

    :param dst_user: The destination user, can be the same as source.
    :type dst_user: str

    :param dst_folder: The destination folder under the destination user.
    :type dst_folder: str

    :param since: The earliest (least recent) internal date of the mails to be moved/copied.
                  The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                  or unix timestamp. `None` means unbounded selection.
    :type since: str

    :param before: The latest (most recent) internal date of the mails to be moved/copied.
                   The date can be one of `None`, ISO-8601 (date only), IMAP4rev1 (date only)
                   or unix timestamp. `None` means unbounded selection.
    :type before: str

    :param copy: Flag designating if the mails should be moved (expunged from the source folder)
                 or copied (remain also in the source folder). `False` = move, `True` = copy
    :type copy: bool

    :return: Nothing.
    :rtype: None
    '''
    if folder_has_mails_to_process(user, folder, since, before):
        if not folder_exists(dst_user, dst_folder):
            create_folder(dst_user, dst_folder)
        move_mails(user, folder, dst_user, dst_folder, since, before, copy)


def parse_datetime(value):
    '''
    Parses represenation of a date/time given by the user, attempts to match one of the accepted
    formats and transforms it into a value which is usable further in the script.

    :param value: Representation of a date/time. Can be one of `None`, unix timestamp,
                  ISO-8601 (date only), IMAP4rev1 (date only) or a human readable representation
                  of elapsed time such as "2 months".
    :type value: str

    :raises: ValueError: ValueError is raised when the method fails to match the representation
                         against one of the expected formats.

    :return: Tuple of (string, int) containing date/time string usable further in the script
             and the most recent year to process, which will be used in case the user wants
             to split the folders by year.
    :rtype: tuple
    '''
    # Empty value means "now"
    if not value:
        return (None, datetime.datetime.now().year)

    # All digits means unix timestamp (e.g. 1609372800), but check if it's later than 1990
    # to prevent unexpected runs when the user forgets to quote human readable representation
    try:
        timestamp = int(value)
        dt = datetime.datetime.fromtimestamp(timestamp)
        if dt > datetime.datetime(1990, 1, 1):
            return (value, dt.year)
    except ValueError:
        pass

    # ISO-8601 date format YYYY-MM-DD (e.g. '2020-12-31')
    try:
        dt = datetime.datetime.strptime(value, '%Y-%m-%d')
        return (value, dt.year)
    except ValueError:
        pass

    # IMAP4rev1 date format DD-Mon-YYYY (e.g. '31-Dec-2020')
    try:
        dt = datetime.datetime.strptime(value, '%d-%b-%Y')
        return (value, dt.year)
    except ValueError:
        pass

    # Human readable representation of timedelta (e.g. '12w', '3 months', '1 hr')
    match = re.match(r'''
                     (\d+)\ ?(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:(?:ou)?rs?)?|
                     d(?:ays?)?|w(?:(?:ee)?ks?)?|mo(?:n(?:th)?s?)?|y(?:(?:ea)?rs?)?)$
                     ''', value, re.VERBOSE)
    if not match:
        raise ValueError(f'Unable to parse time representation "{value}"')
    units = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks', 'y': 'years'}
    unit = 'months' if match[2].startswith('mo') else units[match[2][0]]
    kwargs = {unit: int(match[1])}
    dt = datetime.datetime.now() - dateutil.relativedelta.relativedelta(**kwargs)
    if unit in ('days', 'weeks', 'months', 'years'):
        return (dt.strftime('%Y-%m-%d'), dt.year)
    return (str(int(dt.timestamp())), dt.year)


def parse_args(arguments):
    '''
    Parses user supplied arguments from command line.

    :return: User-supplied arguments as argparse namespace object.
    :rtype: argparse.Namespace
    '''
    parser = argparse.ArgumentParser(description=__usage__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    required = parser.add_argument_group('required arguments')
    required.add_argument('--user', '-u', required=True,
                          help='Source user whose mails will be moved.')
    parser.add_argument('--folder', '-f', action='append',
                        help='Source folder which will be moved including its subfolders. ' \
                             'If not given, all user\'s folders will be moved')
    parser.add_argument('--dst-user', '-d',
                        help='Destination user to whom will the mails be moved. ' \
                             'If not given, source user will be used.')
    parser.add_argument('--dst-root-folder', '-r', default='',
                        help='Destination root folder to move the folder structure into, ' \
                             'e.g. \'Archive\'. If not given, root namespace will be used.')
    parser.add_argument('--before', '-b',
                        help='Move only mails sent before this date. The date needs to supplied ' \
                             'as unix timestamp, ISO-8601 (YYY-MM-DD), IMAP4rev1 (DD-Mon-YYYY) ' \
                             'or a human readable representation of elapsed time (e.g. ' \
                             '"2 months", "3y"). If not given, all mails will be moved.')
    parser.add_argument('--split-by-year', '-y', action='store_true',
                        help='Create subfolders with the respective years in the destination ' \
                             'folder structure as ' \
                             '[/dst-root-folder]/<year>/<folder>/<subfolder>. ' \
                             'If not given, folders will be moved as a whole.')
    parser.add_argument('--year-as-last-folder', '-l', action='store_true',
                        help='Create subfolders with the respective years as the last ' \
                             'folder in the hieararchy as ' \
                             '[/dst-root-folder]/<folder>/<subfolder>/<year>. ' \
                             'Effective only when --split-by-year is used.')
    parser.add_argument('--copy', '-c', action='store_true',
                        help='Copy the mails instead of moving. If not given the mails are ' \
                             'removed from the source location after successful move.')
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        help='Print informational (-v) and debug (-vv) messages. If not given, ' \
                             'the tool is silent and outputs only fatal errors.')

    args = parser.parse_args(arguments)

    # If no folder was given by the user, match all folders
    if not args.folder:
        args.folder = ['']

    # Set the destination user to the same as the source one if not explicitly given
    if not args.dst_user:
        args.dst_user = args.user

    return args


def main(command_args=None):
    '''
    Main function to process the user-supplied arguments and run the logic to process
    all folders and mails matching the given criteria.

    :param command_args: User-supplied arguments passed via command line.
    :type command_args: list

    :return: Nothing.
    :rtype: None
    '''

    args = parse_args(command_args)

    if args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose > 1:
        logging.basicConfig(level=logging.DEBUG)

    # Parse datetime representation
    # Also gets the latest year to process in case the user wants to split by years
    before, first_year = parse_datetime(args.before)

    # Get full list of all folders and subfolders to process
    folders = []
    for folder in args.folder:
        folders.extend(get_subfolders(args.user, folder))

    # Process the folders
    if args.split_by_year:
        # Iterate over years in case the user wants to split by years
        # The first processed year (most recent) is always clamped by the 'before' argument
        # Previous years are processed in full
        for year in range(first_year, min(first_year, 2000)-1, -1):
            since = f'{year}-01-01'
            for folder in folders:
                if args.year_as_last_folder:
                    dst_folder = os.path.join(args.dst_root_folder, folder, str(year))
                else:
                    dst_folder = os.path.join(args.dst_root_folder, str(year), folder)
                process_folder(args.user, folder, args.dst_user, dst_folder,
                               since, before, args.copy)
            before = since
    else:
        for folder in folders:
            dst_folder = os.path.join(args.dst_root_folder, folder)
            process_folder(args.user, folder, args.dst_user, dst_folder, None, before, args.copy)
