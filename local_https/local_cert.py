"""Self-signed certificate for testing the site from a phone on the same Wi-Fi.

Phone browsers only allow the live camera on HTTPS pages. This creates a local
certificate for localhost and the laptop's current Wi-Fi IP, and recreates it
when that IP changes. It is for local testing only.
"""

from __future__ import annotations

import datetime
import ipaddress
import socket
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parent / "certs"
CERT_PATH = CERT_DIR / "local-cert.pem"
KEY_PATH = CERT_DIR / "local-key.pem"


def lan_addresses() -> list[str]:
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # UDP connect sends no packets; it only picks the outgoing interface.
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(
        address
        for address in addresses
        if ipaddress.ip_address(address).is_private
        and not ipaddress.ip_address(address).is_loopback
    )


def _covered_addresses() -> set[str]:
    from cryptography import x509

    certificate = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
    names = certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value
    if certificate.not_valid_after_utc <= datetime.datetime.now(datetime.timezone.utc):
        return set()
    return {str(address) for address in names.get_values_for_type(x509.IPAddress)}


def _create_certificate(addresses: list[str]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "BarongClassifier local test")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    alt_names = [x509.DNSName("localhost")] + [
        x509.IPAddress(ipaddress.ip_address(address))
        for address in ["127.0.0.1", *addresses]
    ]
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))


def ensure_certificate() -> tuple[Path, Path, list[str]]:
    """Return (cert, key, lan_ips), creating the certificate when needed."""
    addresses = lan_addresses()
    needs_new = not CERT_PATH.is_file() or not KEY_PATH.is_file()
    if not needs_new:
        try:
            needs_new = not set(addresses) <= _covered_addresses()
        except Exception:
            needs_new = True
    if needs_new:
        _create_certificate(addresses)
    return CERT_PATH, KEY_PATH, addresses
