# Sobel Pipeline on FPGA
Sobel pipeline project to work on an FPGA. I've tested the design on PYNQ-Z1.



## Repository Structure
```bash
├── pynq
│   ├── sobel_pipeline.ipynb    # Jupyter Notebook to run the design on PYNQ-Z1
│   ├── sobel_pipeline_rgb.bit  # Bitstream for PYNQ-Z1 overlay
│   └── sobel_pipeline_rgb.hwh  # Hardware Handoff file for PYNQ-Z1 overlay
├── sim
│   ├── Makefile                # Makefile to run simulation
│   ├── image_hex.py            # Python script to prepare images
│   ├── sample.png              # Sample image for simulation
│   └── testbench.sv            # Testbench module to run the simulation
├── src
│   ├── ram_1r1w_sync.sv        # Synchronous 1r1w RAM module
│   ├── sobel_channel_filter.sv # Sobel filter for a single channel
│   ├── sobel_operator.sv       # Sobel operator to apply the filter on a pixel
│   └── sobel_pipeline.sv       # Top-level module for the design
├── .gitignore                  # Git ignore file
├── LICENSE                     # License file
└── README.md                   # This file
```



## Instructions to Clone
1. Clone the repository:
    ```
    git clone git@github.com:erendn/sobel-pipeline-fpga.git
    ```
1. Install the following dependencies:
    + [Python](https://www.python.org/) >= 3.6
    + [Pillow](https://github.com/python-pillow/Pillow) library for Python
    + [Icarus Verilog](https://github.com/steveicarus/iverilog) and/or [Verilator](https://github.com/verilator/verilator)



## Instructions for Simulation
Run the following commands to simulate the design using `iverilog` and/or `verilator`:
```bash
cd sim
make iverilog   # For iverilog only
make verilator  # For verilator only
make all        # For both
```



## Instructions to Build for PYNQ-Z1
If you want to program this module into PYNQ-Z1, you can create use the AXI DMA interface of the ZYNQ 7000 processor.
Alternatively, you can use the overlay files in the `pynq` folder of this repository.



## Instructions to Run on PYNQ-Z1
You can also use the Jupyter Notebook in the `pynq` folder to run the design on PYNQ-Z1. You need PYNQ v3.0.0 or later
to be able to load the overlay.



* * *


Credits to "Tauraloke" for the sample image: [Original file](https://en.wikipedia.org/wiki/File:Valve_original_%281%29.PNG)
