# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from ufo.automator.app_apis.factory import APIReceiverFactory
from ufo.automator.basic import ReceiverBasic
from ufo.automator.puppeteer import ReceiverManager
from ufo.automator.app_apis.web.selenium_webclient import SeleniumWebReceiver
from ufo import utils


@ReceiverManager.register
class SeleniumWebReceiverFactory(APIReceiverFactory):
    """
    Factory class for Selenium Web receiver.
    """

    def create_receiver(self, app_root_name: str, *args, **kwargs) -> ReceiverBasic:
        """
        Create the Selenium web receiver.
        :param app_root_name: The app root name.
        :return: The receiver.
        """
        if app_root_name not in self.supported_app_roots:
            return None

        selenium_receiver = SeleniumWebReceiver()
        utils.print_with_color(f"Selenium Web receiver created for {app_root_name}.", "green")

        return selenium_receiver

    @property
    def supported_app_roots(self):
        """
        Get the supported app roots.
        """
        return ["selenium_web", "web_automation", "chrome_selenium", "edge_selenium"]

    @classmethod
    def name(cls) -> str:
        """
        The name of the factory.
        """
        return "SeleniumWeb" 