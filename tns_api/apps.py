from django.apps import AppConfig
import logging
import os

logger = logging.getLogger(__name__)


class TnsApiConfig(AppConfig):
    name = 'tns_api'

    def ready(self):
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key:
            masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
            logger.info("OPENAI_API_KEY loaded: %s", masked)
        else:
            logger.warning("OPENAI_API_KEY not set.")
