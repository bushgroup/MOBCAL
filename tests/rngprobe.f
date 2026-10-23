      program rngprobe
c
c     The Philox4x32-10 generator of mobcal_rng.inc, driven from
c     standard input and answered on standard output. Compiled with
c     the include from the fortran directory (gfortran -I). The first
c     record is the number of known-answer vectors, then one record
c     per vector, the four counter words and the two key words as
c     decimal integers, each answered with the four output words as
c     eight hex digits. The last record is a seed, a count n and a
c     skip s: the first n uniforms at that seed as 64-bit patterns,
c     then s draws skipped, then one more uniform.
c
      implicit none
      integer*8 c0,c1,c2,c3,k0,k1,r0,r1,r2,r3
      integer nkat,i,iseed,n,ns
      double precision u,phiuni
c
      read(5,*) nkat
      do 10 i=1,nkat
      read(5,*) c0,c1,c2,c3,k0,k1
      call philox4(c0,c1,c2,c3,k0,k1,r0,r1,r2,r3)
      write(6,600) r0,r1,r2,r3
  600 format(4(z8.8,1x))
   10 continue
      read(5,*) iseed,n,ns
      call rnginit(iseed)
      do 20 i=1,n
      u=phiuni()
      write(6,610) u
  610 format(z16.16)
   20 continue
      call rngskip(ns)
      u=phiuni()
      write(6,610) u
      stop
      end
c
      include 'mobcal_rng.inc'
