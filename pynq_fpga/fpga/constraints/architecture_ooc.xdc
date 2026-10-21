# Architecture-only 100 MHz clock constraint. Board pin LOCs are deliberately
# absent until the checked board manifest is completed from official sources.
create_clock -name sys_clk -period 10.000 [get_ports clk]

