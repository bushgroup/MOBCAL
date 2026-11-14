# A first calculation on Linux

This page takes you from the released package to two calculations in the window, on the examples
that MOBCAL ships with: the choline cation in helium, from the input of the 2012 release, and the
same ion in nitrogen, from an ORCA output with the partial charges that ORCA fitted. It ends with
the help pages and the self-check. Working through it takes about half an hour, and the
calculations take a few minutes of that on a laptop. Each step names the page of this guide that
tells the rest.

## What the package needs

The Linux package runs on x86-64. The window needs Debian 12, Ubuntu 22.04, RHEL 9, or a later
release of a desktop distribution, because the Qt libraries it is built on need the C++ runtime of
GCC 11. The `mobcal` command needs glibc 2.28 or later, which RHEL 8 and its rebuilds (e.g.,
AlmaLinux 8 and CentOS Stream 8), Debian 10, and Ubuntu 20.04 have. To see which glibc a system
has, run

```
ldd --version
```

and read the version on its first line. A system that the command runs on and the window does not
can run both calculations of this page from a terminal ([Without the
window](#without-the-window)). Nothing in the package runs on CentOS 7, whose glibc is 2.17.

## Installing

1. Download `mobcal-<version>-linux-x86_64.tar.gz` from the
   [Releases page](https://github.com/bushgroup/MOBCAL/releases) of the repository.
2. Unpack it into your home folder, which gives the folder `mobcal-<version>`, and put that folder
   on your `PATH`:

   ```
   tar -xzf ~/Downloads/mobcal-<version>-linux-x86_64.tar.gz -C ~
   export PATH="$HOME/mobcal-<version>:$PATH"
   ```

   The `export` line holds for this terminal only. To run `mobcal` in every new terminal, add the
   same line to `~/.bashrc`, or to the startup file of your shell.
3. Run the self-check, which takes about a second, prints one line for each stage of the check,
   and ends with "self-check passed":

   ```
   mobcal self-check
   ```

[Installing MOBCAL](install.md#linux-x86-64) says what the package carries and how each build is
tested.

## Copying the examples

The package keeps the examples in `~/mobcal-<version>/examples`. To keep the files you work on
apart from the installation, which an upgrade replaces, copy them to a folder of your own:

```
cp -r ~/mobcal-<version>/examples ~/Documents/"MOBCAL examples"
```

It holds `Choline.mfj`, the choline input of the 2012 release, and `choline_sp.out`, an ORCA
output of the same ion, which the two calculations below use, and a Gaussian output and the 2012
reference outputs, which they do not.

## Opening the window

In a terminal in which `mobcal` runs, run

```
mobcal gui
```

The form is on the left: Inputs, Method, Basics, Advanced, and Results folder, with the estimate
under them. The Queue, Progress, and Results are on the right. At the first launch the method is
**MOBCAL 2012 with Philox (He)**, the calculation of the 2012 release in helium with a newer random
number generator, and the results folder is `MOBCAL results` in your Documents folder. Every
control has a tooltip that says what it sets.

## Choline in helium

1. Choose **Add files…**, open `MOBCAL examples` in Documents, and choose `Choline.mfj`. Its row
   in Inputs gives 21 atoms, 1 coordinate set, charges "from file", net charge "+1", and the status
   "ready".
2. Read the line under the form. It names the method and says how the run will use the cores of
   this computer and about how long it will take, under a minute on a laptop with four to eight
   cores ([The estimate](large-ions.md#the-estimate)).
3. Choose **Add batch**. The batch appears in the Queue with its estimate. Choose **Start queue**.
   While the run is in flight the button reads **Pause queue**, and Progress gives the time the
   run has taken against the estimate.
4. When the run ends, the Results table gives the cross sections in Å²: 55.16 by the trajectory
   method (TM), 60.95 by the projection approximation (PA), and 63.48 by exact hard spheres (EHS),
   with the status "ok". These three numbers are the same on every computer, because the method
   fixes the seed and the programs give the same digits on Windows, macOS, and Linux. They differ
   from the 2012 values, 55.402, 61.075, and 63.473 Å², because the 2012 release drew its random
   numbers from another generator; the self-check below reproduces those
   ([Methods](methods.md#the-five-shipped-methods)).
5. Choose **Copy methods text** and paste into a text editor or a word processor. The paragraph
   describes the run from its record, i.e., the program and version, the method, the gas, the
   element table, the temperature, the trajectory counts, the generator, and the seed, and lists
   the papers to cite.
6. Select the row and choose **Show in folder**. The file manager opens the run directory,
   `Choline-he-5013489`, which holds the output of the program, `mobcal.out`, the result file,
   `Choline-he-5013489.result.json`, and the record of the run, `record.json` ([The results
   folder](results-folder.md)).

## An ORCA output in nitrogen

1. Select the `Choline.mfj` row in Inputs and choose **Remove**. Choose **Add files…** and choose
   `choline_sp.out` from `MOBCAL examples`. The window imports the output as `mobcal import` does.
   Its row gives 21 atoms and the net charge, 1, read from the output, and the Charges list offers
   each set of charges the output holds: "mulliken", "lowdin", "hirshfeld", "chelpg", and "uniform
   (Q/N on every atom)". The CHELPG charges, which ORCA fitted to the electrostatic potential, are
   selected. Keep them ([Choosing the charges](import.md#choosing-the-charges)).
2. In the Method list, choose **MOBCAL 2012 with Philox (N2)**. The gas under Basics changes to
   N2, and the line under the form gives the estimate for nitrogen, which is 9 to 17 min on a
   laptop with four to eight cores, because a trajectory in nitrogen costs about 25 times one in
   helium.
3. To finish in a few minutes instead, open Advanced at its arrow and change `imp`, the
   trajectories in each block, from 1,000 to 250. The Method list now reads "Custom (from MOBCAL
   2012 with Philox (N2))", and the estimate falls to 2 to 4 min. The price is precision. A quarter
   of the trajectories doubles the scatter between the 10 cycles of the calculation, from 0.7 % to
   1.5 % of the cross section for this ion ([The run settings](settings.md#what-the-values-are)).
4. Choose **Add batch**, then **Start queue**. The run gives a TM cross section of 115.32 Å², again
   the same on every computer. At the full 1,000 trajectories per block the same ion gives
   115.65 Å².
5. Select the row and choose **Open output**. Near the end, `mobcal.out` gives the scatter as
   "standard deviation (percent) = 1.5088E+00".
6. Choose **Copy methods text** and paste it beside the first. This paragraph also names the
   partial charges: the CHELPG charges from ORCA 6.1.1, with the keywords of the calculation.
   The window wrote the imported ion to `imported/choline_sp_chelpg.ion.json` in the results
   folder, and the run read that file, which carries the record of where the charges came from
   ([The ion file](ion-file.md)).
7. Choose **Save CSV…** and save the table. The file holds both rows, with the input, the run
   count, and the folder of each.

To set `imp` back to 1,000, choose a method in the Method list again, which fills every field of
the form.

## The help pages

Choose **Help ▸ MOBCAL Help**, or press F1. The help window lists every page of this guide, this
one among them, and the search box above the contents finds a word on every page at once. The
pages are the ones the package was built with, so the help needs no network connection.

## The self-check

The check run after installing takes about a second. A longer check also runs the 2012 choline
input under the method of the 2012 release and compares the three cross sections with the 2012
output. In a terminal in which `mobcal` runs, run

```
mobcal self-check --choline
```

It takes about three minutes and ends with "self-check passed". Under the choline stage, three
lines give each cross section beside its value in the 2012 output, 61.075 (PA), 63.473 (EHS), and
55.402 Å² (TM), and the two agree ([Checking an installation](install.md#checking-an-installation)).

## Without the window

On a system without the window, or without a display, the same two calculations run from a
terminal. In the folder of the examples,

```
cd ~/Documents/"MOBCAL examples"
mobcal run Choline.mfj --split auto --out ~/Documents/"MOBCAL results"
mobcal import choline_sp.out --charges chelpg
mobcal run choline_sp_chelpg.ion.json --method 2012-philox-n2 --imp 250 --split auto --out ~/Documents/"MOBCAL results"
mobcal methods-text ~/Documents/"MOBCAL results"
```

runs choline in helium, writes the ORCA output as an ion file with its CHELPG charges, runs that
file in nitrogen with `imp` at 250, and prints the methods paragraph for both runs. Each run
prints its cross sections, the numbers the window gives to one more digit, and `summary.csv` in the results
folder holds both rows ([The command line](command-line.md)).

## Next

[The window](window.md) describes every control used here and the ones that were not, e.g.,
several seeds per ion, the three ways a batch uses the cores, and saving a method of your own.
[Importing a structure and its charges](import.md) covers Gaussian outputs and `.xyz` files.
[The command line](command-line.md) runs the same calculations from a terminal, with the same
records.
