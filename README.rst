dovecot-archive
===============

dovecot-archive is a ``doveadm`` wrapper for common mail archival tasks.

Usage
-----

required arguments:

``--user USER, -u USER``
    Source user whose mails will be moved.

optional arguments:

``--folder FOLDER, -f FOLDER``
    Source folder which will be moved including its subfolders. If not given, all user's folders will be moved

``--dst-user DST_USER, -d DST_USER``
    Destination user to whom will the mails be moved. If not given, source user will be used.

``--dst-root-folder DST_ROOT_FOLDER, -r DST_ROOT_FOLDER``
    Destination root folder to move the folder structure into, e.g. 'Archive'. If not given, root namespace will be used.

``--before BEFORE, -b BEFORE``
    Move only mails sent before this date. The date needs to supplied as unix timestamp, ISO-8601 (YYY-MM-DD), IMAP4rev1 (DD-Mon-YYYY) or a human readable representation of elapsed time (e.g. "2 months", "3y"). If not given, all mails will be moved.

``--split-by-year, -y``
    Create subfolders with the respective years in the destination folder structure as [/dst-root-folder]/<year>/<folder>/<subfolder>. If not given, folders will be moved as a whole.

``--year-as-last-folder, -l``
    Create subfolders with the respective years as the last folder in the hieararchy as [/dst-root-folder]/<folder>/<subfolder>/<year>. Effective only when --split-by-year is used.

``--copy, -c``
    Copy the mails instead of moving. If not given the mails are removed from the source location after successful move.

``--verbose, -v``
    Print informational (-v) and debug (-vv) messages. If not given, the tool is silent and outputs only fatal errors.

Use cases
---------

Scenario 1)
^^^^^^^^^^^

I have way too many mails and it makes my e-mail client slow. I want to move sent and received mails older than 3 years to a different user/account (which I only open in my e-mail client when I really need to), and I want to retain the same folder structure of the mailboxes as I have under the current user/account. I don't want to archive thrash, spam, etc.

Create a weekly cron task:

.. code-block:: bash

    dovecot-archive --user original.user@example.com --dst-user archival.user@example.com --folder INBOX --folder Sent --before "3 years"

Scenario 2)
^^^^^^^^^^^

I have way too many mails and I want to move mails older than 14 days into an archive folder under the same user/account. I also want to create a subfolder for every year.

Create a daily cron task:

.. code-block:: bash

    dovecot-archive --user user@example.com --folder INBOX --dst-root-folder Archive --split-by-year --before "14 days"

Scenario 3)
^^^^^^^^^^^

An employee is leaving the company and I want to move all their mail to a new user/account of the employee replacing them. I want to move the whole folder structure, but to place it under a subfolder so it doesn't interfere with the new empolyee's mails.

Manually run once:

.. code-block:: bash

    dovecot-archive --user leaver@example.com --dst-user joiner@example.com --dst-root-folder "Jane Doe"
