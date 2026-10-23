c
c     ***************************************************************
c
c     The atom bound, len, and the four common blocks it dimensions:
c     the partial charges, the coordinates (fx, fy, fz as rotated, ox,
c     oy, oz as read), the Lennard-Jones parameters and the hard-sphere
c     radii of every atom. Until 2026 each routine that used them
c     repeated these lines. fx, fy and fz hold one more element than
c     the bound, because MOBIL4 keeps the incidence vector of a
c     projection trajectory in slot inatom+1 and rotates it with the
c     atoms.
c
c     This file is included by every routine of mobcal_He.f and
c     mobcal_N2.f that uses the atom arrays.
c
c     ***************************************************************
c
      parameter (len=200000)
      common/charge/pcharge(len)
      common/coordinates/fx(len+1),fy(len+1),fz(len+1),
     ?ox(len),oy(len),oz(len)
      common/ljparameters/eolj(len),rolj(len),eox4(len),
     ?ro6lj(len),ro12lj(len),dro6(len),dro12(len)
      common/hsparameters/rhs(len),rhs2(len)
