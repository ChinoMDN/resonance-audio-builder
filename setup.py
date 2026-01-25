from setuptools import setup, find_packages

setup(
    name="resonance-audio-builder",
    version="6.0.0",
    description="Personal audio library builder with metadata and loudness normalization",
    author="ChinoMDN",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "yt-dlp",
        "mutagen",
        "rich",
        "requests",
    ],
    entry_points={
        "console_scripts": [
            "resonance-audio-builder = resonance_audio_builder.cli:main",
        ]
    },
)
