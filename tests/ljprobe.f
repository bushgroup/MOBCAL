      program ljprobe
c
c     Every row of the element table at full precision, through the
c     program's own reader. Compiled with mobcal_ljread.inc from the
c     fortran directory (gfortran -I), run where a parameters.tab is,
c     with the gas (He or N2) on standard input. For each row: the key
c     and the mass, well depth, radius and hard-sphere radius that
c     FCOORD and NCOORD would assign an atom of that key, as 64-bit
c     patterns. A refusal goes to probe.txt and the screen, status 1.
c
      implicit double precision (a-h,m-z)
      character*2 gas
      parameter (ltab=100)
      common/ljtable/xmtab(ltab),eptab(ltab),rotab(ltab),rhtab(ltab),
     ?itab,ktab(ltab)
c
      read(5,'(a2)') gas
      open(8,file='probe.txt')
      call ljread(gas)
      xe=1.60217733d-19
      do 10 i=1,itab
      call ljparm(ktab(i),xe,itest,xm,e,r,rh)
      write(8,600) ktab(i),itest,xm,e,r,rh
  600 format(i4,1x,i1,4(1x,z16.16))
   10 continue
      close (8)
      stop
      end
c
      include 'mobcal_ljread.inc'
