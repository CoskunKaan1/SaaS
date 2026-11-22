"""API bağlayıcıları.

Gerçek bir sistemde buradaki bağlayıcılar şirketin kullandığı harici/dahili
API'lere istek atıp yanıttaki tüketim bilgisini (token, sayfa, istek) okur.
Bu projede gerçek API'ler çağrılamayacağı için ``SimulatedApiConnector``
aynı sözleşmeyle gerçekçi yanıtlar üretir; ``testusers`` paketi de bu
bağlayıcıyı kullanan sanal kullanıcıları çalıştırır.
"""

from core.connectors.base import ApiConnector, ApiResponse
from core.connectors.simulated_api import SimulatedApiConnector

__all__ = ["ApiConnector", "ApiResponse", "SimulatedApiConnector"]
