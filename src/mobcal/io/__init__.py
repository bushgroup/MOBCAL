"""The file formats of the 2012 program: ``.mfj`` input, ``mobcal.in`` and the ``.out`` file.

``mfj`` reads an input the way ``fcoord`` and ``ncoord`` do and refuses what they would stop on;
``infile`` writes the three-record run file; ``outfile`` normalizes an output for comparison
with the 2012 references and reads its SUMMARY block. Pure functions and data, no subprocesses
and no Qt.
"""
