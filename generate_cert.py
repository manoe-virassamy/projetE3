"""Génère un certificat TLS auto-signé pour servir l'app en HTTPS sur le réseau local.

À lancer une fois avant le premier démarrage (ou si l'IP locale change) :
    python generate_cert.py [--ip 10.188.39.14]

Écrit certs/cert.pem et certs/key.pem, lus par .streamlit/config.toml.
"""
import argparse
import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERTS_DIR = Path(__file__).parent / "certs"


def detecter_ip_lan() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # aucun paquet réellement envoyé, juste pour choisir la bonne carte réseau
        return s.getsockname()[0]
    finally:
        s.close()


def generer_certificat(ip_lan: str) -> None:
    CERTS_DIR.mkdir(exist_ok=True)

    cle = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    sujet = emetteur = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "BlindClimb Assist (local)"),
    ])

    maintenant = datetime.datetime.now(datetime.timezone.utc)
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address(ip_lan)),
    ])

    certificat = (
        x509.CertificateBuilder()
        .subject_name(sujet)
        .issuer_name(emetteur)
        .public_key(cle.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(maintenant - datetime.timedelta(days=1))
        .not_valid_after(maintenant + datetime.timedelta(days=825))
        .add_extension(san, critical=False)
        # Sans ça, iOS ne reconnaît pas ce certificat auto-signé comme une autorité
        # racine valide : il n'apparaît pas dans "Réglages de confiance des
        # certificats" même après installation du profil.
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=True, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        # Exigé par les règles ATS d'Apple pour qu'un certificat serveur TLS soit accepté.
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(cle, hashes.SHA256())
    )

    (CERTS_DIR / "key.pem").write_bytes(
        cle.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (CERTS_DIR / "cert.pem").write_bytes(certificat.public_bytes(serialization.Encoding.PEM))


def main():
    parser = argparse.ArgumentParser(description="Génère certs/cert.pem et certs/key.pem")
    parser.add_argument("--ip", help="Force l'IP locale à inclure dans le certificat (sinon détection auto)")
    args = parser.parse_args()

    ip_lan = args.ip or detecter_ip_lan()
    generer_certificat(ip_lan)

    print(f"Certificat généré dans {CERTS_DIR}\\ (IP incluse : {ip_lan})")
    print()
    print("Lancement de l'app :")
    print("    streamlit run app.py --server.address 0.0.0.0")
    print()
    print(f"Accès depuis le téléphone (même Wi-Fi) : https://{ip_lan}:8501")
    print("Le navigateur affichera un avertissement « connexion non privée » la première fois")
    print("(certificat auto-signé) : acceptez-le pour continuer (« Avancé » puis « Continuer »).")


if __name__ == "__main__":
    main()
