"""Sanal (test) kullanıcılar.

Uygulama açıldığı andan itibaren bu paketteki motor, veritabanında
``SimulationProfiles`` kaydı olan kullanıcılar adına gerçekmiş gibi API
çağrıları üretir ve kredi harcar.
"""

from core.connectors.testusers.factory import TestUserError, attach_user, create_test_user
from core.connectors.testusers.personas import PERSONAS
from core.connectors.testusers.simulator import SimulationEngine

__all__ = ["PERSONAS", "SimulationEngine", "TestUserError", "attach_user", "create_test_user"]
