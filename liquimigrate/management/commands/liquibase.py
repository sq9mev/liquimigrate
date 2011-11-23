from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management.sql import emit_post_sync_signal
from django.core.management import call_command
from liquimigrate import LIQUIBASE_JAR, LIQUIBASE_DRIVERS

try:
    from django.db import connections
    databases = connections.databases
except ImportError:
    # django without multidb support
    databases = {
            'default': {
                'ENGINE': settings.DATABASE_ENGINE,
                'HOST': settings.DATABASE_HOST,
                'PORT': settings.DATABASE_PORT,
                'NAME': settings.DATABASE_NAME,
                'USER': settings.DATABASE_USER,
                'PASSWORD': settings.DATABASE_PASSWORD,
            },
        }

from optparse import make_option
import os
        
DB_DEFAULTS = {
    'postgresql': {
        'tag': 'postgresql',
        'host': 'localhost',
        'port': 5432,
    },
    'mysql': {
        'tag': 'mysql',
        'host': 'localhost',
        'port': 3306,
    },
}

class Command(BaseCommand):
    help = "liquibase migrations"

    option_list = BaseCommand.option_list + (
        make_option('', '--changeLogFile', dest='changelog_file',
            help='XML file with changelog'),
        make_option('', '--driver', dest='driver',
            help='db driver'),
        make_option('', '--classpath', dest='classpath',
            help='jdbc driver class path'),
        make_option('', '--username', dest='username',
            help='db username'),
        make_option('', '--password', dest='password',
            help='db password'),
        make_option('', '--url', dest='url',
            help='db url'),
        )

    def handle(self, *args, **options):
        """
        Handle liquibase command parameters
        """
        database = getattr(settings, 'LIQUIMIGRATE_DATABASE', 'default')
        
        dbsettings = databases[database]

        # get driver
        driver_class = options.get('driver') or dbsettings.get('ENGINE').split('.')[-1]
        dbtag, driver, classpath = LIQUIBASE_DRIVERS.get(driver_class, ( None, None, None))
        classpath = options.get('classpath') or classpath
        if driver is None:
            raise CommandError("unsupported db driver '%s'\navailable drivers: %s" % (driver_class, ' '.join(LIQUIBASE_DRIVERS.keys())))

        # command options 
        changelog_file = options.get('changelog_file') or settings.LIQUIMIGRATE_CHANGELOG_FILE
        username = options.get('username') or dbsettings.get('USER') or ''
        password = options.get('password') or dbsettings.get('PASSWORD') or ''
        url = options.get('url') or _get_url_for_db(dbtag, dbsettings)

        if len(args) < 1:
            raise CommandError("give me any command, for example 'update'")

        command = args[0]
        cmdargs = {
            'jar': LIQUIBASE_JAR,
            'changelog_file': changelog_file,
            'username': username,
            'password': password,
            'command': command,
            'driver': driver,
            'classpath': classpath,
            'url': url,
            'args': ' '.join(args[1:]),
        }

        cmdline = "java -jar %(jar)s --changeLogFile %(changelog_file)s \
--username=%(username)s --password=%(password)s \
--driver=%(driver)s --classpath=%(classpath)s --url=%(url)s \
%(command)s %(args)s" % ( cmdargs)

        print "executing: %s" % (cmdline,)
        rc = os.system( cmdline)

        if rc == 0:
            created_models = None   # we dont know it
            
            try:
                emit_post_sync_signal(
                    created_models, 0,
                    options.get('interactive'), database)

                call_command('loaddata', 'initial_data',
                    verbosity=0,
                    database=database)
            except TypeError:
                # singledb (1.1 and older)
                emit_post_sync_signal(
                    created_models, 0,
                    options.get('interactive'))
                call_command('loaddata', 'initial_data',
                    verbosity=0)


def _get_url_for_db(tag, dbsettings):
    pattern = "jdbc:%(tag)s://%(host)s:%(port)s/%(name)s"
    options = dict(DB_DEFAULTS.get(tag) or {})
    options.update({
            'name': dbsettings.get('NAME') or options.get('name', ''),
            'host': dbsettings.get('HOST') or options.get('host', ''),
            'port': dbsettings.get('PORT') or options.get('port', ''),
    })
    return pattern % options 

