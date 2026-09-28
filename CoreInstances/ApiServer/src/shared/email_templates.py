"""
Email templates for automated system responses.

Plain-text templates used by the extraction worker and email intake worker.
"""

NAME_MISMATCH_REJECTION = (
    "Hello,\n\n"
    "The certificate you submitted does not appear to be yours. "
    "The name on the certificate does not match your employee record.\n\n"
    "If this is your certificate, please contact the Certification Coordinator "
    "for assistance. Otherwise, please have the certificate holder email it "
    "from their own city email address, or forward it to the Coordinator for "
    "manual processing.\n\n"
    "Thank you,\n"
    "City of Laredo Certificate Management System"
)
