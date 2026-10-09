"""Run Django's development server with a supplied TLS certificate."""

import ssl

from django.contrib.staticfiles.management.commands.runserver import (
    Command as RunserverCommand,
)


class Command(RunserverCommand):
    help = "Starts Django's development server over HTTPS using a certificate and key."
    protocol = "https"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--certificate",
            required=True,
            help="Path to the TLS certificate PEM file.",
        )
        parser.add_argument(
            "--key",
            required=True,
            help="Path to the TLS private key PEM file.",
        )

    def get_handler(self, *args, **options):
        application = super().get_handler(*args, **options)

        def https_application(environ, start_response):
            environ["wsgi.url_scheme"] = "https"
            return application(environ, start_response)

        return https_application

    def inner_run(self, *args, **options):
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(options["certificate"], options["key"])
        base_server_class = self.server_cls

        class TLSWSGIServer(base_server_class):
            def get_request(server):
                request, client_address = super().get_request()
                return tls_context.wrap_socket(request, server_side=True), client_address

        self.server_cls = TLSWSGIServer
        try:
            super().inner_run(*args, **options)
        finally:
            self.server_cls = base_server_class
