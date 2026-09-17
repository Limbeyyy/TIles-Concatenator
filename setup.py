from setuptools import setup, find_packages
import os

# Read requirements
with open('requirements.txt', 'r') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read version from setup config
VERSION = '0.0.8'
DESCRIPTION = 'Tile Concatenator - High-resolution map tile capture and stitching tool'

setup(
    name='Tile-Concatenator',
    version=VERSION,
    author='Baikuntha',
    author_email='baikuntha@ramlaxmangroup.com',
    description=DESCRIPTION,
    long_description=open('README.md', 'r').read() if os.path.exists('README.md') else DESCRIPTION,
    long_description_content_type='text/markdown',
    url='https://github.com/Limbeyyy/TIles-Concatenator',
    packages=find_packages(where='src/app'),
    package_dir={'': 'src/app'},
    install_requires=requirements,
    python_requires='>=3.8',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Environment :: X11 Applications :: GTK',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Topic :: Scientific/Engineering :: GIS',
        'Topic :: Multimedia :: Graphics',
    ],
    keywords='map tile capture satellite imagery geospatial',
    entry_points={
        'console_scripts': [
            'tile-concatenator=Map_Concator_App:main',
        ],
        'gui_scripts': [
            'tile-concatenator-gui=Map_Concator_App:main',
        ],
    },
    include_package_data=True,
    package_data={
        '': ['media/*', '*.ico', '*.png'],
    },
)
