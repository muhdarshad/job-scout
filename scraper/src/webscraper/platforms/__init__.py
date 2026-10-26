"""Platform scrapers for different career site platforms."""

from .workday import WorkdayPlatform
from .mercedes import MercedesPlatform
from .siemens import SiemensEnergyPlatform
from .lufthansa import LufthansaPlatform
from .alten import AltenPlatform
from .bmw import BMWPlatform
from .bosch import BoschPlatform
from .n3 import N3Platform
from .honeywell import HoneywellPlatform
from .boeing import BoeingPlatform
from .everllence import EverllencePlatform
from .siemens_ag import SiemensAGPlatform
from .dhl import DHLPlatform
from .mtu import MTUPlatform
from .audi import AudiPlatform
from .liebherr import LiebherrPlatform
from .volkswagen import VolkswagenPlatform
from .diehl import DiehlPlatform
from .smartrecruiters import SmartRecruitersPlatform
from .emirates import EmiratesPlatform
from .man import MANPlatform

PLATFORMS = {
    "workday": WorkdayPlatform(),
    "mercedes_successfactors": MercedesPlatform(),
    "siemens_energy": SiemensEnergyPlatform(),
    "lufthansa": LufthansaPlatform(),
    "alten": AltenPlatform(),
    "bmw": BMWPlatform(),
    "bosch": BoschPlatform(),
    "n3": N3Platform(),
    "honeywell": HoneywellPlatform(),
    "boeing": BoeingPlatform(),
    "everllence": EverllencePlatform(),
    "siemens_ag": SiemensAGPlatform(),
    "dhl": DHLPlatform(),
    "mtu": MTUPlatform(),
    "audi": AudiPlatform(),
    "liebherr": LiebherrPlatform(),
    "volkswagen": VolkswagenPlatform(),
    "diehl": DiehlPlatform(),
    "smartrecruiters": SmartRecruitersPlatform(),
    "emirates": EmiratesPlatform(),
    "man": MANPlatform(),
}


def get_platform(platform_name: str):
    """Get platform scraper by name."""
    return PLATFORMS.get(platform_name)



