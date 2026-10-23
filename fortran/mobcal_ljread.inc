c
c     ***************************************************************
c
c     The element table. Until 2026 each program assigned every atom
c     its mass, Lennard-Jones well depth and radius and hard-sphere
c     radius from a chain of if(imass(iatom).eq.NN) blocks in FCOORD
c     and again in NCOORD. The table is now read once, by LJREAD, from
c     the file parameters.tab in the working directory, which the
c     mobcal package renders from its data file for the gas before
c     every run; FCOORD and NCOORD look each atom up with LJPARM. The
c     numbers are the 2012 numbers: every token is converted by the
c     kind the 2012 source gave it, and each quantity is evaluated
c     term for term as the 2012 statement evaluated it.
c
c     This file is included by mobcal_He.f and mobcal_N2.f.
c
c     ***************************************************************
c
      subroutine ljread(gas)
c
c     Reads parameters.tab. Its lines: a header naming the format
c     (MOBCAL-LJ 1), the gas, the set and the hash of the file it was
c     rendered from; the kind in bytes, 4 or 8, of the mass, well
c     depth, radius and hard-sphere columns; in nitrogen the four
c     combining constants eogas, rogas, conve, convr; the number of
c     rows; and one row per element, its integer mass key and four
c     tokens. Each token is read as text and converted by its column's
c     kind, so that a literal the 2012 source spelled in single
c     precision gives the number the compiled source gave. The set's
c     name and hash are printed to the screen; the output file gains
c     no line. A table that is missing, not of this format, for the
c     other gas, or longer than ltab rows is refused with status 1.
c
      implicit double precision (a-h,m-z)
      character*2 gas
      parameter (ltab=100)
      common/ljtable/xmtab(ltab),eptab(ltab),rotab(ltab),rhtab(ltab),
     ?itab,ktab(ltab)
      character*16 magic
      character*2 tgas
      character*60 tname
      character*64 thash
      character*32 tok(4)
      dimension ikind(4),val(4)
      real s4
c
      open(21,file='parameters.tab',status='old',iostat=ios)
      if(ios.ne.0) then
      write(8,601)
      write(6,601)
  601 format(1x,'parameter table parameters.tab not found in the ',
     ?'working directory; mobcal run writes it')
      close (8)
      stop 1
      endif
c
      read(21,*,iostat=ios) magic,ifmt,tgas,tname,thash
      if(ios.ne.0.or.magic.ne.'MOBCAL-LJ'.or.ifmt.ne.1) then
      write(8,602)
      write(6,602)
  602 format(1x,'parameters.tab is not a MOBCAL-LJ 1 table')
      close (8)
      stop 1
      endif
      if(tgas.ne.gas) then
      write(8,603) tgas,gas
      write(6,603) tgas,gas
  603 format(1x,'parameters.tab is a table for ',a2,
     ?'; this program is for ',a2)
      close (8)
      stop 1
      endif
c
      read(21,*,iostat=ios) (ikind(j),j=1,4)
      if(ios.ne.0) goto 90
      do 10 j=1,4
      if(ikind(j).ne.4.and.ikind(j).ne.8) then
      write(8,604) ikind(j)
      write(6,604) ikind(j)
  604 format(1x,'parameters.tab declares a kind of',i4,
     ?' bytes; 4 or 8 are read')
      close (8)
      stop 1
      endif
   10 continue
c
c     nitrogen: the combining constants, double precision, as the
c     2012 source assigned them before each chain
c
      if(gas.eq.'N2') then
      read(21,*,iostat=ios) (tok(j),j=1,4)
      if(ios.ne.0) goto 90
      read(tok(1),*,iostat=ios) eogas
      if(ios.ne.0) goto 90
      read(tok(2),*,iostat=ios) rogas
      if(ios.ne.0) goto 90
      read(tok(3),*,iostat=ios) conve
      if(ios.ne.0) goto 90
      read(tok(4),*,iostat=ios) convr
      if(ios.ne.0) goto 90
      endif
c
      read(21,*,iostat=ios) itab
      if(ios.ne.0) goto 90
      if(itab.lt.1.or.itab.gt.ltab) then
      write(8,605) itab,ltab
      write(6,605) itab,ltab
  605 format(1x,'parameters.tab has',i6,' rows; 1 to',i4,
     ?' are allowed')
      close (8)
      stop 1
      endif
c
c     each row: the key, then the four tokens converted by kind and
c     promoted; the well depth and radius evaluated as the 2012
c     statements did, up to the factor xe or 1.0d-10 that LJPARM
c     applies per atom
c
      do 20 i=1,itab
      read(21,*,iostat=ios) ktab(i),(tok(j),j=1,4)
      if(ios.ne.0) goto 90
      do 15 j=1,4
      if(ikind(j).eq.4) then
      read(tok(j),*,iostat=ios) s4
      val(j)=dble(s4)
      else
      read(tok(j),*,iostat=ios) val(j)
      endif
      if(ios.ne.0) goto 90
   15 continue
      xmtab(i)=val(1)
      if(gas.eq.'N2') then
      eptab(i)=dsqrt(eogas*val(2))*conve
      rotab(i)=dsqrt(rogas*val(3))*convr
      else
      eptab(i)=val(2)
      rotab(i)=val(3)
      endif
      rhtab(i)=val(4)
   20 continue
      close (21)
c
      l=60
   30 if(tname(l:l).eq.' '.and.l.gt.1) then
      l=l-1
      goto 30
      endif
      write(6,606) tname(1:l),thash
  606 format(1x,'parameter set ',a,1x,a64)
      return
c
   90 write(8,607)
      write(6,607)
  607 format(1x,'parameters.tab cannot be read as a MOBCAL-LJ 1 ',
     ?'table')
      close (8)
      stop 1
      end
c
c     ***************************************************************
c
      subroutine ljparm(key,xe,itest,xm,e,r,rh)
c
c     Looks one atom's integer mass key up in the table LJREAD read
c     and assigns its mass, well depth, radius and hard-sphere radius
c     as the 2012 statements did: the well depth times xe, the two
c     radii times 1.0d-10. itest is 1 when the key is in the table and
c     0 when it is not, which the caller refuses with its format 602.
c
      implicit double precision (a-h,m-z)
      parameter (ltab=100)
      common/ljtable/xmtab(ltab),eptab(ltab),rotab(ltab),rhtab(ltab),
     ?itab,ktab(ltab)
c
      itest=0
      do 10 i=1,itab
      if(ktab(i).eq.key) then
      itest=1
      xm=xmtab(i)
      e=eptab(i)*xe
      r=rotab(i)*1.0d-10
      rh=rhtab(i)*1.0d-10
      endif
   10 continue
      return
      end
