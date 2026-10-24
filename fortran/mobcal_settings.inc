c
c     ***************************************************************
c
c     The run settings. Until 2026 the temperature and the five
c     sampling counts were constants assigned in the main program:
c     t = 301 K; imp, the trajectories per block in MOBIL2; itn, its
c     cycles; inp, its velocity points; inum, the trajectories of
c     MOBIL4; inor, the reflections MOBIL4 follows. SETREAD assigns
c     those same values, then reads the file settings.tab from the
c     working directory if there is one, which the mobcal package
c     renders from its settings file and the user's choices before a
c     run. Without the file the program computes what the 2012 program
c     computed. A value outside the bounds below is refused with
c     status 1 before anything is calculated.
c
c     The bounds are the 2012 arrays and formats: itn and inp index
c     arrays of 100 in MOBIL2, inor arrays of 100 in MOBIL4; imp is
c     printed with i6, inum with i7, and the total number of points
c     itn*inp*imp with i7. The mobcal package holds the same bounds
c     and refuses first; tools/check_public.py compares the two.
c
c     This file is included by mobcal_He.f and mobcal_N2.f.
c
c     ***************************************************************
c
      subroutine setread(t,imp,itn,inp,inum,inor)
c
c     Reads settings.tab. Its lines: a header naming the format
c     (MOBCAL-SETTINGS 1), then the temperature and the five counts,
c     t imp itn inp inum inor, as blank-separated tokens. The
c     temperature is read as double precision from a literal the
c     package writes with seventeen significant digits, which gives
c     back the package's number to the bit; 301 reads as the compiled
c     301.d0 did. The values are printed to the screen; the output
c     file gains no line.
c
      implicit double precision (a-h,m-z)
      integer mximp,mxitn,mxinp,mxinum,mxinor,mxtot
      parameter (mximp=999999)
      parameter (mxitn=100)
      parameter (mxinp=100)
      parameter (mxinum=9999999)
      parameter (mxinor=100)
      parameter (mxtot=9999999)
      character*16 magic
      logical lset
c
c     the 2012 values
c
      t=301.d0
      imp=1000
      itn=10
      inp=40
      inum=250000
      inor=30
c
      inquire(file='settings.tab',exist=lset)
      if(.not.lset) return
      open(21,file='settings.tab',status='old',iostat=ios)
      if(ios.ne.0) goto 90
      read(21,*,iostat=ios) magic,ifmt
      if(ios.ne.0.or.magic.ne.'MOBCAL-SETTINGS'.or.ifmt.ne.1) then
      write(8,601)
      write(6,601)
  601 format(1x,'settings.tab is not a MOBCAL-SETTINGS 1 file')
      close (8)
      stop 1
      endif
      read(21,*,iostat=ios) t,imp,itn,inp,inum,inor
      if(ios.ne.0) goto 90
      close(21)
c
      if(.not.(t.gt.0.d0.and.t.lt.1.d300)) then
      write(8,602) t
      write(6,602) t
  602 format(1x,'settings.tab: temperature',1pe12.4,
     ?' is not a positive number')
      close (8)
      stop 1
      endif
      if(imp.lt.1.or.imp.gt.mximp) then
      write(8,603) 'imp',imp,mximp
      write(6,603) 'imp',imp,mximp
      close (8)
      stop 1
      endif
      if(itn.lt.1.or.itn.gt.mxitn) then
      write(8,603) 'itn',itn,mxitn
      write(6,603) 'itn',itn,mxitn
      close (8)
      stop 1
      endif
      if(inp.lt.1.or.inp.gt.mxinp) then
      write(8,603) 'inp',inp,mxinp
      write(6,603) 'inp',inp,mxinp
      close (8)
      stop 1
      endif
      if(inum.lt.1.or.inum.gt.mxinum) then
      write(8,603) 'inum',inum,mxinum
      write(6,603) 'inum',inum,mxinum
      close (8)
      stop 1
      endif
      if(inor.lt.1.or.inor.gt.mxinor) then
      write(8,603) 'inor',inor,mxinor
      write(6,603) 'inor',inor,mxinor
      close (8)
      stop 1
      endif
  603 format(1x,'settings.tab: ',a,' is',i11,'; 1 to',i8,
     ?' are allowed')
c
c     the product in double precision: at the bounds above it exceeds
c     a default integer
c
      if(dfloat(itn)*dfloat(inp)*dfloat(imp).gt.dfloat(mxtot)) then
      write(8,604) itn,inp,imp,mxtot
      write(6,604) itn,inp,imp,mxtot
  604 format(1x,'settings.tab: itn*inp*imp is',i4,'*',i4,'*',i7,
     ?'; at most',i8,' points per coordinate set')
      close (8)
      stop 1
      endif
c
      write(6,605) t,imp,itn,inp,inum,inor
  605 format(1x,'settings from settings.tab: t=',1pe11.4,' imp=',i7,
     ?' itn=',i4,' inp=',i4,' inum=',i8,' inor=',i4)
      return
c
   90 write(8,606)
      write(6,606)
  606 format(1x,'settings.tab cannot be read as a MOBCAL-SETTINGS 1 ',
     ?'file')
      close (8)
      stop 1
      end
