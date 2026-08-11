import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="kuest-py-clob-client",
    version="2.0.11",
    author="Kuest Engineering",
    author_email="engineering@kuest.com",
    maintainer="Kuest Engineering",
    maintainer_email="engineering@kuest.com",
    description="Python client for the Kuest CLOB",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kuestcom/py-clob-client",
    install_requires=[
        "eth-account>=0.13.7",
        "eth-abi>=5.2.0",
        "eth-utils>=6.0.0",
        "kuest-py-eip712-structs==0.0.4",
        "kuest-py-order-utils==0.3.7",
        "python-dotenv>=1.2.2",
        "kuest-py-builder-signing-sdk==2.0.2",
        "httpx[http2]>=0.28.1",
    ],
    project_urls={
        "Bug Tracker": "https://github.com/kuestcom/py-clob-client/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    packages=setuptools.find_packages(),
    python_requires=">=3.10",
)
