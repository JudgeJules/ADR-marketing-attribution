from setuptools import setup, find_packages

setup(
    name="attribution",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.11",
    install_requires=[
        "flask>=3.0.0",
        "flask-cors>=4.0.0",
        "apscheduler>=3.10.4",
        "google-ads>=21.3.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
    ],
)
