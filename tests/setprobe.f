      program setprobe
c
c     The run settings at full precision, through the program's own
c     reader. Compiled with mobcal_settings.inc from the fortran
c     directory (gfortran -I), run in a directory with or without a
c     settings.tab. Prints the temperature as a 64-bit pattern and the
c     five counts to probe.txt. A refusal goes to probe.txt and the
c     screen, status 1, as it does in the programs.
c
      implicit double precision (a-h,m-z)
c
      open(8,file='probe.txt')
      call setread(t,imp,itn,inp,inum,inor)
      write(8,600) t,imp,itn,inp,inum,inor
  600 format(z16.16,5(1x,i8))
      close (8)
      stop
      end
c
      include 'mobcal_settings.inc'
