.. _ref_guide_cloud_deploy_netlify:

=======
Netlify
=======

:edb-alt-title: Deploying applications built on Gel Cloud to Netlify

.. note::

    This guide assumes the Git deployment method on Netlify, but you may also
    deploy your site using other methods. Just make sure the Gel Cloud
    environment variables are set, and your app should have connectivity to
    your instance.

1. Push project to GitHub or some other Git remote repository
2. Create and make note of a secret key for your Gel Cloud instance
3. On your Netlify Team Overview view under Sites, click Import from Git
4. Import your project's repository
5. Configure the build settings appropriately for your app
6. Click the Add environment variable button
7. Use the New variable button to add two variables:

   - :gelenv:`INSTANCE` containing your Gel Cloud instance name (in
     ``<org>/<instance-name>`` format)
   - :gelenv:`SECRET_KEY` containing the secret key you created and noted
     previously.

8. Click Deploy

.. image:: images/cloud-netlify-config.png
    :width: 100%
    :alt: A screenshot of the Netlify deployment configuration view
          highlighting the environment variables section where a user will
          need to set the necessary variables for Gel Cloud instance
          connection.
