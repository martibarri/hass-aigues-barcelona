"""Platform for sensor integration."""
#from __future__ import annotations

from homeassistant.core import HomeAssistant, CoreState, callback
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_STATE,
    EVENT_HOMEASSISTANT_START,
    UnitOfVolume,
)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_CONTRACT,
)

from .api import AiguesApiClient

from datetime import timedelta
from datetime import datetime
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry,
    async_add_entities
):
    """Set up entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.info("calling async_setup_entry")

    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    contract = config_entry.data[CONF_CONTRACT]

    platform = entity_platform.async_get_current_platform()

    coordinator = ContratoAgua(
        hass,
        username,
        password,
        contract,
        prev_data=None
    )

    # postpone first refresh to speed up startup
    @callback
    async def async_first_refresh(*args):
        """Force the component to assess the first refresh."""
        await coordinator.async_refresh()

    if hass.state == CoreState.running:
        await async_first_refresh()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, async_first_refresh)

    _LOGGER.info("about to add entities")
    # add sensor entities
    async_add_entities([ContadorAgua(coordinator)])

    return True

class ContratoAgua(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        contract: str,
        prev_data=None,
    ) -> None:
        """Initialize the data handler."""
        self.reset = prev_data is None

        self.contract = contract.upper()
        self.id = contract.lower()

        if not hass.data[DOMAIN].get(self.contract):
            # init data shared store
            hass.data[DOMAIN][self.contract] = {}

        # create alias
        self._data = hass.data[DOMAIN][self.contract]

        # the api object
        self._api = AiguesApiClient(
            username,
            password,
            contract
        )

        super().__init__(
            hass,
            _LOGGER,
            name=self.id,
            update_interval=timedelta(minutes=240),
        )

    async def _async_update_data(self):
        _LOGGER.info("Updating coordinator data")
        TODAY = datetime.now()

        previous = self._data.get(CONF_STATE, None)

        if previous and (TODAY - previous) >= timedelta(minutes=60):
            _LOGGER.warn("Skipping request update data - too early")
            return

        try:
            await self.hass.async_add_executor_job(self._api.login)
            consumptions = await self.hass.async_add_executor_job(self._api.consumptions, TODAY)
        except Exception as msg:
            _LOGGER.error("error while getting data: %s", msg)

        if not consumptions:
            _LOGGER.error("No consumptions available")
            return False

        self._data["consumptions"] = consumptions

        # get last entry - most updated
        metric = consumptions[-1]
        self._data["value"] = metric["accumulatedConsumption"]
        self._data[CONF_STATE] = metric["datetime"]

        return True

class ContadorAgua(CoordinatorEntity, SensorEntity):
    """Representation of a sensor."""

    def __init__(self, coordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._data = coordinator.hass.data[DOMAIN][coordinator.id.upper()]
        self._attr_name = f"Contador {coordinator.name}"
        self._attr_unique_id = coordinator.id
        self._attr_icon = "mdi:water-pump"
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        #self._attr_state = None
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
        self._attr_state_class = "total"

    @property
    def native_value(self):
        return self._data.get("value", -1)