.. _ref_cli_gel_cloud_secretkey_revoke:


==========================
gel cloud secretkey revoke
==========================

Revoke a secret key

.. cli:synopsis::

    gel cloud secretkey revoke [<options>] --secret-key-id <secret-key-id>

.. note::

    This command works only if you have already authenticated using
    :ref:`ref_cli_gel_cloud_login`.

Options
=======

:cli:synopsis:`--json`
    Output results as JSON
:cli:synopsis:`--secret-key-id <secret_key_id>`
    Id of secret key to revoke
:cli:synopsis:`-y, --non-interactive`
    Revoke the key without asking for confirmation.
