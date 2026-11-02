"""The file formats of the 2012 program: ``.mfj`` input, ``mobcal.in`` and the ``.out`` file;
and the ion file, ``X.ion.json``, from which a ``.mfj`` is written per run.

``mfj`` reads an input the way ``fcoord`` and ``ncoord`` do and refuses what they would stop on;
``ion`` reads, checks and writes the ion file and converts it to and from a ``.mfj``;
``mobcalmpi`` reads MobCal-MPI's nine-column ``.mfj``, an import source for an ion file;
``infile`` writes the three-record run file; ``outfile`` normalizes an output for comparison
with the 2012 references and reads its SUMMARY block. Pure functions and data, no Qt, and no
subprocess but the ``git`` that names the commit an ion file records (``mobcal.fortran._commit``).
"""
