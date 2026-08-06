"""Self-signed TLS certs so phone browsers allow getUserMedia on the LAN."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path


def ensure_desktop_tls(data_dir: Path, lan_ip: str) -> tuple[Path, Path]:
    """Return (cert_path, key_path), creating a LAN-friendly self-signed cert if needed."""
    cert_dir = data_dir / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "desktop.crt"
    key_path = cert_dir / "desktop.key"
    meta_path = cert_dir / "lan_ip.txt"

    previous_ip = meta_path.read_text(encoding="utf-8").strip() if meta_path.exists() else ""
    if cert_path.exists() and key_path.exists() and previous_ip == lan_ip:
        return cert_path, key_path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IntelliQuiz Desktop"),
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip or "IntelliQuiz"),
        ]
    )

    san: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
    ]
    try:
        san.append(x509.IPAddress(ipaddress.ip_address(lan_ip)))
    except ValueError:
        if lan_ip:
            san.append(x509.DNSName(lan_ip))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    meta_path.write_text(lan_ip, encoding="utf-8")
    return cert_path, key_path
