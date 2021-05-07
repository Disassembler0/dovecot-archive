import argparse
import datetime
import logging
import mock
import os
import pytest
import subprocess
import dovecot_archive


# Reliable datetime mock from https://blog.xelnor.net/python-mocking-datetime/
real_datetime_class = datetime.datetime

def mock_datetime_now(target, dt):
    class DatetimeSubclassMeta(type):
        @classmethod
        def __instancecheck__(mcs, obj):
            return isinstance(obj, real_datetime_class)

    class BaseMockedDatetime(real_datetime_class):
        @classmethod
        def now(cls, tz=None):
            return target.replace(tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return target # pragma: no cover

    MockedDatetime = DatetimeSubclassMeta('datetime', (BaseMockedDatetime,), {})
    return mock.patch.object(dt, 'datetime', MockedDatetime)


@pytest.mark.parametrize('value,expected', [
    (None, (None, 2021)),
    ('', (None, 2021)),
    ('2019-05-10', ('2019-05-10', 2019)),
    ('31-Dec-2020', ('31-Dec-2020', 2020)),
    ('1613665392', ('1613665392', 2021)),
    ('3 years', ('2018-02-18', 2018)),
    ('3yrs', ('2018-02-18', 2018)),
    ('3y', ('2018-02-18', 2018)),
    ('6 months', ('2020-08-18', 2020)),
    ('6 mon', ('2020-08-18', 2020)),
    ('6mo', ('2020-08-18', 2020)),
    ('12 weeks', ('2020-11-26', 2020)),
    ('12wks', ('2020-11-26', 2020)),
    ('12 w', ('2020-11-26', 2020)),
    ('14 days', ('2021-02-04', 2021)),
    ('14d', ('2021-02-04', 2021)),
    ('2 hours', ('1613595600', 2021)),
    ('2hrs', ('1613595600', 2021)),
    ('2h', ('1613595600', 2021)),
    ('5 minutes', ('1613602500', 2021)),
    ('5m', ('1613602500', 2021)),
    ('5 mins', ('1613602500', 2021)),
    ('30 seconds', ('1613602770', 2021)),
    ('30 s', ('1613602770', 2021)),
    ('30secs', ('1613602770', 2021)),
])
def test_parse_datetime(value, expected):
    with mock_datetime_now(datetime.datetime(2021, 2, 18), datetime):
        assert dovecot_archive.parse_datetime(value) == expected

@pytest.mark.parametrize('value', [
    '100',
    'years',
    '2mi',
    '9001 moths',
    '7 apples',
    'bubblegum',
])
def test_parse_datetime_exception(value):
    with pytest.raises(ValueError):
        dovecot_archive.parse_datetime(value)


def test_mailbox_path_join():
    path1 = dovecot_archive.mailbox_path_join('INBOX', 'folder')
    path2 = dovecot_archive.mailbox_path_join('INBOX', 'folder', 'subfolder', separator='.')

    assert path1 == 'INBOX/folder'
    assert path2 == 'INBOX.folder.subfolder'


@mock.patch('subprocess.run')
def test_run(run):
    dovecot_archive.run(['ls', '-la'], param='test')

    run.assert_called_once_with(['ls', '-la'],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=True,
                                param='test')


@mock.patch('dovecot_archive.run')
def test_get_subfolders(run):
    run.return_value.stdout = b'INBOX/folder1\nINBOX/folder2\nINBOX'

    result = dovecot_archive.get_subfolders('user', 'INBOX')

    run.assert_called_once_with(['doveadm', 'mailbox', 'list', '-u', 'user', 'INBOX*'],
                                stdout=subprocess.PIPE)

    assert result == ['INBOX/folder1', 'INBOX/folder2', 'INBOX']


@mock.patch('dovecot_archive.run')
def test_folder_exists_true(run):
    result = dovecot_archive.folder_exists('user', 'folder')

    run.assert_called_once_with(['doveadm', 'mailbox', 'status',
                                 '-u', 'user', 'messages', 'folder'])
    assert result

@mock.patch('dovecot_archive.run', side_effect=subprocess.CalledProcessError(1, 'cmd'))
def test_folder_exists_false(run):
    result = dovecot_archive.folder_exists('user', 'folder')

    run.assert_called_once_with(['doveadm', 'mailbox', 'status',
                                 '-u', 'user', 'messages', 'folder'])
    assert not result


@mock.patch('dovecot_archive.run')
def test_create_folder(run):
    dovecot_archive.create_folder('user', 'folder')

    run.assert_has_calls([
        mock.call(['doveadm', 'mailbox', 'create', '-u', 'user', 'folder']),
        mock.call(['doveadm', 'mailbox', 'subscribe', '-u', 'user', 'folder']),
    ])
    assert run.call_count == 2

@pytest.mark.parametrize('stdout,expected', [
    (b'mail', True),
    (b'', False),
])
@mock.patch('dovecot_archive.run')
def test_folder_has_mails_to_process_all(run, stdout, expected):
    run.return_value.stdout = stdout
    result = dovecot_archive.folder_has_mails_to_process('user', 'folder', None, None)

    run.assert_called_once_with(['doveadm', 'search', '-u', 'user', 'mailbox', 'folder', 'all'],
                                stdout=subprocess.PIPE)

    assert result == expected

@mock.patch('dovecot_archive.run')
def test_folder_has_mails_to_process_since(run):
    dovecot_archive.folder_has_mails_to_process('user', 'folder', '2019-01-01', None)

    run.assert_called_once_with(['doveadm', 'search', '-u', 'user', 'mailbox', 'folder',
                                 'since', '2019-01-01'], stdout=subprocess.PIPE)

@mock.patch('dovecot_archive.run')
def test_folder_has_mails_to_process_before(run):
    dovecot_archive.folder_has_mails_to_process('user', 'folder', None, '2020-01-01')

    run.assert_called_once_with(['doveadm', 'search', '-u', 'user', 'mailbox', 'folder',
                                 'before', '2020-01-01'], stdout=subprocess.PIPE)

@mock.patch('dovecot_archive.run')
def test_folder_has_mails_to_process_since_before(run):
    dovecot_archive.folder_has_mails_to_process('user', 'folder', '2019-01-01', '2020-01-01')

    run.assert_called_once_with(['doveadm', 'search', '-u', 'user', 'mailbox', 'folder',
                                 'since', '2019-01-01', 'before', '2020-01-01'],
                                stdout=subprocess.PIPE)


@mock.patch('dovecot_archive.run')
def test_move_mails_all(run):
    dovecot_archive.move_mails('user', 'folder', 'user', 'dstfolder', None, None, False)

    run.assert_called_once_with(['doveadm', 'move', '-u', 'user', 'dstfolder', 'mailbox', 'folder',
                                 'all'])

@mock.patch('dovecot_archive.run')
def test_move_mails_all_copy(run):
    dovecot_archive.move_mails('user', 'folder', 'user', 'dstfolder', None, None, True)

    run.assert_called_once_with(['doveadm', 'copy', '-u', 'user', 'dstfolder', 'mailbox', 'folder',
                                 'all'])

@mock.patch('dovecot_archive.run')
def test_move_mails_all_dstuser(run):
    dovecot_archive.move_mails('srcuser', 'folder', 'dstuser', 'dstfolder', None, None, False)

    run.assert_called_once_with(['doveadm', 'move', '-u', 'dstuser', 'dstfolder', 'user',
                                 'srcuser', 'mailbox', 'folder', 'all'])

@mock.patch('dovecot_archive.run')
def test_move_mails_since(run):
    dovecot_archive.move_mails('user', 'folder', 'user', 'dstfolder', '2019-01-01', None, False)

    run.assert_called_once_with(['doveadm', 'move', '-u', 'user', 'dstfolder', 'mailbox', 'folder',
                                 'since', '2019-01-01'])

@mock.patch('dovecot_archive.run')
def test_move_mails_before(run):
    dovecot_archive.move_mails('user', 'folder', 'user', 'dstfolder', None, '2020-01-01', False)

    run.assert_called_once_with(['doveadm', 'move', '-u', 'user', 'dstfolder', 'mailbox', 'folder',
                                 'before', '2020-01-01'])

@mock.patch('dovecot_archive.run')
def test_move_mails_since_before(run):
    dovecot_archive.move_mails('user', 'folder', 'user', 'dstfolder',
                               '2019-01-01', '2020-01-01', False)

    run.assert_called_once_with(['doveadm', 'move', '-u', 'user', 'dstfolder', 'mailbox', 'folder',
                                 'since', '2019-01-01', 'before', '2020-01-01'])


@mock.patch('dovecot_archive.folder_has_mails_to_process', return_value=True)
@mock.patch('dovecot_archive.folder_exists', return_value=False)
@mock.patch('dovecot_archive.create_folder')
@mock.patch('dovecot_archive.move_mails')
def test_process_folder(move_mails, create_folder, folder_exists, folder_has_mails_to_process):
    dovecot_archive.process_folder('user', 'folder', 'dstuser', 'dstfolder',
                                   '2019-01-01', '2020-01-01', False)

    folder_has_mails_to_process.assert_called_once_with('user', 'folder', '2019-01-01',
                                                        '2020-01-01')
    folder_exists.assert_called_once_with('dstuser', 'dstfolder')
    create_folder.assert_called_once_with('dstuser', 'dstfolder')
    move_mails.assert_called_once_with('user', 'folder', 'dstuser', 'dstfolder',
                                       '2019-01-01', '2020-01-01', False)

@mock.patch('dovecot_archive.folder_has_mails_to_process', return_value=True)
@mock.patch('dovecot_archive.folder_exists', return_value=True)
@mock.patch('dovecot_archive.create_folder')
@mock.patch('dovecot_archive.move_mails')
def test_process_folder_dst_exists(move_mails, create_folder, folder_exists,
                                   folder_has_mails_to_process):
    dovecot_archive.process_folder('user', 'folder', 'dstuser', 'dstfolder',
                                   '2019-01-01', '2020-01-01', False)

    folder_has_mails_to_process.assert_called_once_with('user', 'folder', '2019-01-01',
                                                        '2020-01-01')
    folder_exists.assert_called_once_with('dstuser', 'dstfolder')
    create_folder.assert_not_called()
    move_mails.assert_called_once_with('user', 'folder', 'dstuser', 'dstfolder',
                                       '2019-01-01', '2020-01-01', False)

@mock.patch('dovecot_archive.folder_has_mails_to_process', return_value=False)
@mock.patch('dovecot_archive.folder_exists')
@mock.patch('dovecot_archive.create_folder')
@mock.patch('dovecot_archive.move_mails')
def test_process_folder_no_mails(move_mails, create_folder, folder_exists,
                                 folder_has_mails_to_process):
    dovecot_archive.process_folder('user', 'folder', 'dstuser', 'dstfolder',
                                   '2019-01-01', '2020-01-01', False)

    folder_has_mails_to_process.assert_called_once_with('user', 'folder', '2019-01-01',
                                                        '2020-01-01')
    folder_exists.assert_not_called()
    create_folder.assert_not_called()
    move_mails.assert_not_called()


def test_parse_args():
    result = dovecot_archive.parse_args(['--user', 'user@example.com'])

    assert result == argparse.Namespace(before=None,
                                        copy=False,
                                        user='user@example.com',
                                        dst_root_folder='',
                                        dst_user='user@example.com',
                                        folder=[''],
                                        split_by_year=False,
                                        year_as_last_folder=False,
                                        namespace_separator='/',
                                        verbose=0)

def test_parse_args_none():
    with pytest.raises(SystemExit):
        dovecot_archive.parse_args([])

def test_parse_args_all():
    result = dovecot_archive.parse_args(['--user', 'srcuser@example.com',
                                         '--folder', 'srcfolder',
                                         '--dst-user', 'dstuser@example.com',
                                         '--dst-root-folder', 'dstfolder',
                                         '--before', '3 months',
                                         '--split-by-year',
                                         '--year-as-last-folder',
                                         '--copy',
                                         '--namespace-separator', '.',
                                         '--verbose'])

    assert result == argparse.Namespace(before='3 months',
                                        copy=True,
                                        user='srcuser@example.com',
                                        dst_root_folder='dstfolder',
                                        dst_user='dstuser@example.com',
                                        folder=['srcfolder'],
                                        split_by_year=True,
                                        year_as_last_folder=True,
                                        namespace_separator='.',
                                        verbose=1)


# --user user@example.com
@mock.patch('logging.basicConfig')
@mock.patch('dovecot_archive.get_subfolders', return_value=['INBOX', 'Sent'])
@mock.patch('dovecot_archive.process_folder')
def test_main(process_folder, get_subfolders, logging_config):
    dovecot_archive.main(['--user', 'user@example.com'])

    logging_config.assert_not_called()
    get_subfolders.assert_called_once_with('user@example.com', '')
    process_folder.assert_has_calls([
        mock.call('user@example.com', 'INBOX', 'user@example.com', 'INBOX', None, None, False),
        mock.call('user@example.com', 'Sent', 'user@example.com', 'Sent', None, None, False),
    ])

# --user user@example.com --dst-root-folder Archive --before '3 years' --split-by-year -v
@mock.patch('logging.basicConfig')
@mock.patch('dovecot_archive.get_subfolders', return_value=['INBOX', 'Sent'])
@mock.patch('dovecot_archive.process_folder')
def test_main2(process_folder, get_subfolders, logging_config):
    with mock_datetime_now(datetime.datetime(2005, 2, 18), datetime):
        dovecot_archive.main(['--user', 'user@example.com',
                              '--dst-root-folder', 'Archive',
                              '--before', '3 years',
                              '--split-by-year',
                              '-v'])

    logging_config.assert_called_once_with(level=logging.INFO)
    get_subfolders.assert_called_once_with('user@example.com', '')
    process_folder.assert_has_calls([
        mock.call('user@example.com', 'INBOX', 'user@example.com',
                  os.path.join('Archive', '2002', 'INBOX'), '2002-01-01', '2002-02-18', False),
        mock.call('user@example.com', 'Sent', 'user@example.com',
                  os.path.join('Archive', '2002', 'Sent'), '2002-01-01', '2002-02-18', False),
        mock.call('user@example.com', 'INBOX', 'user@example.com',
                  os.path.join('Archive', '2001', 'INBOX'), '2001-01-01', '2002-01-01', False),
        mock.call('user@example.com', 'Sent', 'user@example.com',
                  os.path.join('Archive', '2001', 'Sent'), '2001-01-01', '2002-01-01', False),
        mock.call('user@example.com', 'INBOX', 'user@example.com',
                  os.path.join('Archive', '2000', 'INBOX'), '2000-01-01', '2001-01-01', False),
        mock.call('user@example.com', 'Sent', 'user@example.com',
                  os.path.join('Archive', '2000', 'Sent'), '2000-01-01', '2001-01-01', False),
    ])


# --user user@example.com --folder INBOX --dst-user dstuser@example.com --before '31-Oct-1995'
# --split-by-year --year-as-last-folder -vv
@mock.patch('logging.basicConfig')
@mock.patch('dovecot_archive.get_subfolders', return_value=['INBOX', 'INBOX/Work'])
@mock.patch('dovecot_archive.process_folder')
def test_main3(process_folder, get_subfolders, logging_config):
    dovecot_archive.main(['--user', 'user@example.com',
                          '--folder', 'INBOX',
                          '--dst-user', 'dstuser@example.com',
                          '--before', '31-Oct-1995',
                          '--split-by-year',
                          '--year-as-last-folder',
                          '-vv'])

    logging_config.assert_called_once_with(level=logging.DEBUG)
    get_subfolders.assert_called_once_with('user@example.com', 'INBOX')
    process_folder.assert_has_calls([
        mock.call('user@example.com', 'INBOX', 'dstuser@example.com',
                  os.path.join('INBOX', '1995'), '1995-01-01', '31-Oct-1995', False),
        mock.call('user@example.com', 'INBOX/Work', 'dstuser@example.com',
                  os.path.join('INBOX/Work', '1995'), '1995-01-01', '31-Oct-1995', False),
    ])
