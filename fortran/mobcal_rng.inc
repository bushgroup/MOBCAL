c
c     ***************************************************************
c
c     A second random number generator beside RANLUX: Philox4x32-10,
c     the counter-based generator of Salmon, Moraes, Dror and Shaw
c     (Random123; "Parallel Random Numbers: As Easy as 1, 2, 3",
c     SC 2011), selected by the word philox on the seed record of
c     mobcal.in (i5 = 2; RANLUX, the 2012 generator, is i5 = 1 and
c     is untouched). Draw n is a function of the seed and n alone:
c     the counter is the running count of draws, so a split
c     calculation reaches any block of trajectories by setting the
c     count instead of drawing through the blocks before it, and a
c     worker's blocks are the serial run's by construction.
c
c     PHILOX4 is the block function as Random123 defines it, 32-bit
c     words held in integer*8 and masked. RNGINIT sets the key to
c     (seed, 0) and the count to zero; PHIUNI returns the next
c     uniform and advances the count by one; RNGSKIP advances it by
c     n. Draw n, counting from 1, is counter block (n-1)/2, counter
c     words ((n-1)/2, 0, 0, 0), output words 0 and 1 when n is odd
c     and 2 and 3 when n is even. The uniform is made from 52 bits,
c     the first of the two words and the top 20 bits of the second,
c     plus a half: u = (k + 1/2) / 2^52, an odd multiple of 2^-53
c     between 2^-53 and 1 - 2^-53 inclusive, exact in double
c     precision and never 0 or 1. The count lives here; i6 of
c     /xrandom/ stays the 2012 call count and is not read.
c
c     This file is included by mobcal_He.f and mobcal_N2.f.
c
c     ***************************************************************
c
      subroutine philox4(c0,c1,c2,c3,k0,k1,r0,r1,r2,r3)
c
c     Philox4x32-10: ten rounds on the counter words c0..c3 under the
c     key words k0, k1, giving r0..r3. The multipliers are D2511F53
c     and CD9E8D57, the key bumps 9E3779B9 and BB67AE85, in hex. The
c     64-bit products of a round are formed in MUL32 from 16-bit
c     halves, so no intermediate exceeds 2^34 and nothing relies on
c     overflow.
c
      implicit none
      integer*8 c0,c1,c2,c3,k0,k1,r0,r1,r2,r3
      integer*8 m0,m1,w0,w1,mask
      parameter (m0=3528531795_8,m1=3449720151_8)
      parameter (w0=2654435769_8,w1=3144134277_8)
      parameter (mask=4294967295_8)
      integer*8 x0,x1,x2,x3,y0,y1,hi0,lo0,hi1,lo1
      integer ir
c
      x0=c0
      x1=c1
      x2=c2
      x3=c3
      y0=k0
      y1=k1
      do 10 ir=1,10
      if(ir.gt.1) then
      y0=iand(y0+w0,mask)
      y1=iand(y1+w1,mask)
      endif
      call mul32(m0,x0,hi0,lo0)
      call mul32(m1,x2,hi1,lo1)
      r0=ieor(ieor(hi1,x1),y0)
      r1=lo1
      r2=ieor(ieor(hi0,x3),y1)
      r3=lo0
      x0=r0
      x1=r1
      x2=r2
      x3=r3
   10 continue
      return
      end
c
c     ***************************************************************
c
      subroutine mul32(a,b,hi,lo)
c
c     The 64-bit product of the 32-bit values a and b as two 32-bit
c     words, hi and lo, from the four 16-bit partial products.
c
      implicit none
      integer*8 a,b,hi,lo,ah,al,bh,bl,t0,t1,t2,mask,m16
      parameter (mask=4294967295_8,m16=65535_8)
c
      ah=ishft(a,-16)
      al=iand(a,m16)
      bh=ishft(b,-16)
      bl=iand(b,m16)
      t0=al*bl
      t1=ah*bl+al*bh
      t2=ah*bh
      t0=t0+ishft(iand(t1,m16),16)
      lo=iand(t0,mask)
      hi=t2+ishft(t1,-16)+ishft(t0,-32)
      return
      end
c
c     ***************************************************************
c
      subroutine rnginit(iseed)
c
c     Key (iseed, 0), count zero: the next draw is draw 1.
c
      implicit none
      integer iseed
      integer*8 ndraw,kseed
      common/rngstate/ndraw,kseed
c
      ndraw=0
      kseed=iseed
      return
      end
c
c     ***************************************************************
c
      subroutine rngskip(n)
c
c     Advances the count by n draws, as n calls of PHIUNI would.
c
      implicit none
      integer n
      integer*8 ndraw,kseed
      common/rngstate/ndraw,kseed
c
      ndraw=ndraw+n
      return
      end
c
c     ***************************************************************
c
      double precision function phiuni()
c
c     The next uniform, from the draw count and the key, and the
c     count advanced by one.
c
      implicit none
      integer*8 ndraw,kseed
      common/rngstate/ndraw,kseed
      integer*8 nb,zero,one,r0,r1,r2,r3,hi,lo,k
      double precision two52
      parameter (zero=0_8,one=1_8,two52=4503599627370496.d0)
c
      nb=ishft(ndraw,-1)
      call philox4(nb,zero,zero,zero,kseed,zero,r0,r1,r2,r3)
      if(iand(ndraw,one).eq.zero) then
      hi=r0
      lo=r1
      else
      hi=r2
      lo=r3
      endif
      k=ishft(hi,20)+ishft(lo,-12)
      phiuni=(dble(k)+0.5d0)/two52
      ndraw=ndraw+1
      return
      end
