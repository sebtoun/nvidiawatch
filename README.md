# nvidiawatch
online stores price/stock watcher

## Installation

A working installation of python 3 is required.

Create a virtual env
```
python -m virtualenv venv
```

Install requirements inside the virtual env
```
./venv/Scripts/python -m pip install -r requirements.txt
```

## Usage
Run main.py inside the virtual env
```
./venv/Scripts/python main.py
```

Example: searching for 3070 TI at nvidia store using the GUI
```
./venv/Scripts/python main.py pattern --only-scanners=nvidia "3070 ti" - gui
```
