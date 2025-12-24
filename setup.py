from setuptools import setup

setup(
    name="SpamBack",
    version="0.1.0",
    packages=["spamback"],
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "transformers",
        "torch",
        "numpy",
        "pillow",
        "google-genai",
        "pyobjc-core",
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-Contacts",
    ],
)
