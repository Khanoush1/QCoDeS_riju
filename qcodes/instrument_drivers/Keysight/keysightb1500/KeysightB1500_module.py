import re
from typing import Optional, Tuple, TYPE_CHECKING, Dict, Union, cast

from qcodes import InstrumentChannel
from .message_builder import MessageBuilder
from . import constants
from .constants import ModuleKind, SlotNr
if TYPE_CHECKING:
    from .KeysightB1500 import KeysightB1500


def parse_module_query_response(response: str) -> Dict[SlotNr, str]:
    """
    Extract installed module information from the given string and return the
    information as a dictionary.

    Args:
        response: Response str to `UNT? 0` query.

    Returns:
        Dictionary from slot numbers to model name strings
    """
    pattern = r";?(?P<model>\w+),(?P<revision>\d+)"

    moduleinfo = re.findall(pattern, response)

    return {
        SlotNr(slot_nr): model
        for slot_nr, (model, rev) in enumerate(moduleinfo, start=1)
        if model != "0"
    }


# Pattern to match the spot measurement response against
_pattern = re.compile(
    r"((?P<status>\w)(?P<chnr>\w)(?P<dtype>\w))?"
    r"(?P<value>[+-]\d{1,3}\.\d{3,6}E[+-]\d{2})"
)


def parse_spot_measurement_response(response: str) -> dict:
    """
    Extract measured value and accompanying metadata from the string
    and return them as a dictionary.

    Args:
        response: Response str to spot measurement query.

    Returns:
        Dictionary with measued value and associated metadata (e.g.
        timestamp, channel number, etc.)
    """
    match = re.match(_pattern, response)
    if match is None:
        raise ValueError(f"{response!r} didn't match {_pattern!r} pattern")

    dd = match.groupdict()
    d = cast(Dict[str, Union[str, float]], dd)
    d["value"] = float(d["value"])

    return d


# TODO notes:
# - [ ] Instead of generating a Qcodes InstrumentChannel for each **module**,
#   it might make more sense to generate one for each **channel**


class B1500Module(InstrumentChannel):
    """Base class for all modules of B1500 Parameter Analyzer

    When subclassing,

      - set ``MODULE_KIND`` attribute to the correct module kind
        :class:`~.constants.ModuleKind` that the module is.
      - populate ``channels`` attribute according to the number of
        channels that the module has.

    Args:
        parent: mainframe B1500 instance that this module belongs to
        name: Name of the instrument instance to create. If `None`
            (Default), then the name is autogenerated from the instrument
            class.
        slot_nr: Slot number of this module (not channel number)
    """
    MODULE_KIND: ModuleKind

    def __init__(self, parent: 'KeysightB1500', name: Optional[str], slot_nr,
                 **kwargs):
        # self.channels will be populated in the concrete module subclasses
        # because channel count is module specific
        self.channels: Tuple
        self.slot_nr = SlotNr(slot_nr)

        if name is None:
            number = len(parent.by_kind[self.MODULE_KIND]) + 1
            name = self.MODULE_KIND.lower() + str(number)

        super().__init__(parent=parent, name=name, **kwargs)

    # Response parsing functions as static methods for user convenience
    parse_spot_measurement_response = parse_spot_measurement_response
    parse_module_query_response = parse_module_query_response

    def enable_outputs(self):
        """
        Enables all outputs of this module by closing the output relays of its
        channels.
        """
        # TODO This always enables all outputs of a module, which is maybe not
        # desirable. (Also check the TODO item at the top about
        # InstrumentChannel per Channel instead of per Module.
        msg = MessageBuilder().cn(self.channels).message
        self.write(msg)

    def disable_outputs(self):
        """
        Disables all outputs of this module by opening the output relays of its
        channels.
        """
        # TODO See enable_output TODO item
        msg = MessageBuilder().cl(self.channels).message
        self.write(msg)

    def is_enabled(self) -> bool:
        """
        Check if channels of this module are enabled.

        Returns:
            `True` if *all* channels of this module are enabled. `False`,
            otherwise.
        """
        # TODO If a module has multiple channels, and only one is enabled, then
        # this will return false, which is probably not desirable.
        # Also check the TODO item at the top about InstrumentChannel per
        # Channel instead of per Module.
        msg = (MessageBuilder()
               .lrn_query(constants.LRN.Type.OUTPUT_SWITCH)
               .message
               )
        response = self.ask(msg)
        activated_channels = re.sub(r"[^,\d]", "", response).split(",")

        is_enabled = set(self.channels).issubset(
            int(x) for x in activated_channels
        )
        return is_enabled
