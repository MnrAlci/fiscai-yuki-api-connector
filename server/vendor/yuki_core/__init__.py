"""Read-only Yuki SOAP-client.

Alleen leesmethodes. Schrijfmethodes (ProcessJournal, ProcessSalesInvoices,
uploads, mutaties) zijn bewust niet geïmplementeerd.
"""

from .errors import (YukiError, YukiConfigError, YukiSoapFault, YukiDossierNotFound,
                     YukiAmbiguousDossier, YukiDailyLimitReached)
from .quota import DailyQuota, QuotaStatus
from .response_cache import ResponseCache
from .client import SessionManager, YukiClient, DossierHandle
from .analysis import YearlyTotals, analyze_trial_balance

__all__ = [
    "YukiError", "YukiConfigError", "YukiSoapFault", "YukiDossierNotFound",
    "YukiAmbiguousDossier", "SessionManager", "YukiClient", "DossierHandle",
    "YearlyTotals", "analyze_trial_balance", "YukiDailyLimitReached", "DailyQuota",
    "QuotaStatus", "ResponseCache",
]
__version__ = "0.2.0"
