"""PKI locale hors-ligne : une autorité (CA) propre à la librairie + un certificat serveur.

Pourquoi deux niveaux ?
- La CA est installée UNE SEULE FOIS sur chaque téléphone.
- Le certificat serveur est réémis automatiquement si l'IP du PC change (DHCP) : les téléphones
  continuent de lui faire confiance sans rien refaire.

Garde-fous de sécurité :
- La CA est « name-constrained » : même si sa clé fuitait, elle ne pourrait signer que pour des IP privées
  (10/8, 172.16/12, 192.168/16, 127/8), `localhost` et `*.local`. Elle est inutilisable pour usurper un site public.
- Clés ECDSA P-256 ; certificat serveur 1 an ; clés écrites de façon atomique avec droits restreints.
- Seul le certificat public de la CA est jamais servi par le réseau, jamais une clé privée.
"""
import datetime
import hashlib
import ipaddress
import os
import socket
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from . import db

CERT_DIR = os.path.join(db.DATA_DIR, "certs")
CA_CERT = os.path.join(CERT_DIR, "Librairie-CA.crt")
CA_KEY = os.path.join(CERT_DIR, "ca.key")
SRV_CERT = os.path.join(CERT_DIR, "server.crt")
SRV_KEY = os.path.join(CERT_DIR, "server.key")

CA_DAYS = 1825          # 5 ans (les racines ne sont pas soumises à la limite de 398 j)
SERVER_DAYS = 365
RENEW_BEFORE_DAYS = 30

PRIVATE_NETS = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _restrict_permissions(path):
    """Droits minimaux : lecture/écriture pour l'utilisateur courant uniquement."""
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME")
            if user:
                subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
                               capture_output=True, timeout=10, check=False)
        else:
            os.chmod(path, 0o600)
    except Exception:
        pass


def _atomic_write(path, data, private=False):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    if private:
        _restrict_permissions(tmp)
    os.replace(tmp, path)


def _pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _pem_cert(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _load_ca():
    with open(CA_CERT, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    with open(CA_KEY, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    return cert, key


def ensure_ca():
    """Charge la CA locale ou la crée si absente / expirée."""
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(CA_CERT) and os.path.exists(CA_KEY):
        cert, key = _load_ca()
        if cert.not_valid_after_utc > _now() + datetime.timedelta(days=RENEW_BEFORE_DAYS):
            return cert, key

    key = ec.generate_private_key(ec.SECP256R1())
    host = socket.gethostname()
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"Librairie Local CA ({host})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Librairie"),
    ])
    permitted = [x509.IPAddress(ipaddress.ip_network(n)) for n in PRIVATE_NETS]
    permitted += [x509.DNSName("localhost"), x509.DNSName("local")]
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(minutes=5))
            .not_valid_after(_now() + datetime.timedelta(days=CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    _atomic_write(CA_KEY, _pem_key(key), private=True)
    _atomic_write(CA_CERT, _pem_cert(cert))
    # Une nouvelle CA invalide l'ancien certificat serveur
    for stale in (SRV_CERT, SRV_KEY):
        if os.path.exists(stale):
            os.remove(stale)
    return cert, key


def _required_sans(ips):
    host = socket.gethostname().lower()
    dns = ["localhost"]
    if host and all(c.isalnum() or c == "-" for c in host):
        dns.append(f"{host}.local")
    return dns, ["127.0.0.1"] + [i for i in ips if i != "127.0.0.1"]


def _server_cert_ok(ca_cert, dns, ips):
    if not (os.path.exists(SRV_CERT) and os.path.exists(SRV_KEY)):
        return False
    try:
        with open(SRV_CERT, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        if cert.issuer != ca_cert.subject:
            return False
        if cert.not_valid_after_utc < _now() + datetime.timedelta(days=RENEW_BEFORE_DAYS):
            return False
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        have_dns = {d.lower() for d in san.get_values_for_type(x509.DNSName)}
        have_ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
        return set(dns) <= have_dns and set(ips) <= have_ips
    except Exception:
        return False


def ensure_server_cert(ips):
    """Garantit un certificat serveur valide couvrant les IP actuelles. Retourne (cert_path, key_path)."""
    ca_cert, ca_key = ensure_ca()
    dns, ip_list = _required_sans(ips)
    if _server_cert_ok(ca_cert, dns, ip_list):
        return SRV_CERT, SRV_KEY

    key = ec.generate_private_key(ec.SECP256R1())
    sans = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ip_list]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Librairie")]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(minutes=5))
            .not_valid_after(_now() + datetime.timedelta(days=SERVER_DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _atomic_write(SRV_KEY, _pem_key(key), private=True)
    _atomic_write(SRV_CERT, _pem_cert(cert) + _pem_cert(ca_cert))   # chaîne complète
    return SRV_CERT, SRV_KEY


def ca_pem():
    """Certificat PUBLIC de la CA (à installer sur les téléphones)."""
    with open(CA_CERT, "rb") as f:
        return f.read()


def ca_fingerprint():
    """Empreinte SHA-256 de la CA, à comparer visuellement entre le PC et le téléphone."""
    cert = x509.load_pem_x509_certificate(ca_pem())
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


if __name__ == "__main__":
    from . import security
    c, k = ensure_server_cert(security.local_ips())
    print("OK", c, ca_fingerprint(), file=sys.stdout)
