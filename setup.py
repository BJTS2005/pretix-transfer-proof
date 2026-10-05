from setuptools import setup, find_packages

setup(
    name="pretix-transfer-proof",
    version="1.0.0",
    description="Transferencia con datos de cuenta y comprobante PNG/JPG/JPEG",
    author="Bryan Tandayamo",
    license="AGPL-3.0-only WITH pretix-additional-terms",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["pretix", "Pillow"],
    entry_points="""
[pretix.plugin]
pretix_transferproof=pretix_transferproof
""",
)
