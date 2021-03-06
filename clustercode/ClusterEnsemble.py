import MDAnalysis
import MDAnalysis.lib.NeighborSearch as NeighborSearch
import warnings
import matplotlib.pyplot as plt
from clustercode.BaseUniverse import BaseUniverse

# from MDAnalysis.core.groups import ResidueGroup
"""
ToDo:
    Make sure PBC do what we want
    Ensure behaviour for gro files
    Make paths to BaseUniverse universal
"""


class ClusterEnsemble(BaseUniverse):
    """A class used to perform analysis on Clusters of molecules

    Attributes
    ----------
    universe : MDAnalysis universe object
        Universe of the simulated system
    cluster_objects : list of str
        Strings used for the definition of species which form
        clusters. Can be atom names or molecule names.
    cluster_list : list of list of MDAnalysis ResidueGroups
        a list of ResidueGroups forms one cluster at a given time,
        for multiple times a list of these lists is produced.

    Methods
    -------
    cluster_analysis(cut_off=7.5, style="atom", measure="b2b",
                     algorithm="static")
        Calculates which molecules are clustering together for all
        timesteps.
    """

    def __init__(self, coord, traj, cluster_objects):
        """
        Parameters
        ----------
        coord : string
            Path to a coordinate-like file. E.g. a gromacs tpr or
            gro file
        traj : string
            Path to a trajectory like file. E.g. a xtc or trr file.
            Needs to fit the coord file
        cluster_objects : list of string
            Strings used for the definition of species which form
            clusters. Can be atom names or molecule names.
        """
        super().__init__(coord, traj, cluster_objects)


    def cluster_analysis(self, cut_off=7.5, times=None, style="atom", 
                    measure="b2b", algorithm="dynamic", work_in="Residue",
                    traj_pbc_style=None, pbc=True):
        """High level function clustering molecules together

        Example
        -------
        No Example yet

        Note
        ----
        Not all of the functionality is actually coded yet

        Parameters
        ----------
        cut_off : float, optional
            Minimal distance for two particles to be in the
            same cluster, in Angstroem. Results still depend
            on the measure parameter.
        time : list of floats, optional
            If None, do for whole trajectory. If an interval
            is given like this (t_start, t_end) only do from start
            to end.
        style : string, optional
            "atom" or "molecule". Dependent on this, the
            cluster_objects attribute is interpreted as molecule
            or atoms within a molecule.
        measure : string, optional
            "b2b (bead to bead), COM or COG(center of geometry)
        algorithm : string, optional
            "dynamic" or "static". The static one is slower. I
            loops over all atoms and then merges cluster, whereas
            the dynamic algorithm grows clusters dynamically.
        work_in : string, optional
            "Residue" or "Atom". Either work in (and output)
            ResidueGroups or AtomGroups.
            The former may be faster for systems in which all
            parts of the same molecule are always in the same cluster,
            whereas the latter is useful for systems in which different
            parts of the same molecule can be in different clusters
            (i.e. block copolymers).
        traj_pbc_style : string, optional
            Gromacs pbc definitions: mol or atom, by default
            None
        pbc : bool, optional
            Whether to consider periodic boundary conditions in the 
            neighbour search (for determining whether atoms belong to
            the same cluster), by default True. Note that if work_in is 
            set to "Residue" periodic boundary conditions are taken into
            account implicitly for atoms in molecules passing across the 
            boundaries.

        Raises
        ------
        NotImplementedError
            If an unspecified algorithm or work_in is choosen
        ValueError
            If pbc is not boolean
        
        ToDo
        ----
        -Make static and dynamic algorithms store the same arguments
        -Add plotting capabilities
        -Add capabilities to only look at certain time windows
        -Get rid of traj and coord attributes
        """

        self._set_pbc_style(traj_pbc_style)

        self.universe = self._get_universe(self._coord, traj=self._traj)

        self.style = style

        self.aggregate_species = self._select_species(self.universe, style=self.style)

        self.cluster_list = []

        # Initialise the neighboursearch object

        if pbc == True:
            self.neighbour_search = NeighborSearch.AtomNeighborSearch(
            self.aggregate_species, 
            box=self.universe.dimensions,
            bucket_size=10
            )
        elif pbc == False:
            if work_in == "Residue" and traj_pbc_style != "mol":
                warnings.warn('work_in = "Residue" implicitly enforces pbc '\
                              'for atoms in the same molecule if pbc_style '\
                              '= "atom"', UserWarning)
                print('Warning')
            self.neighbour_search = NeighborSearch.AtomNeighborSearch(
                self.aggregate_species, 
                box=None,
                bucket_size=10
                )
        else:
            raise ValueError("pbc has to be boolean")

        if work_in == "Residue":
            self.search_level = "R"
        elif work_in == "Atom":
            self.search_level = "A"
        else:
            raise NotImplementedError(
                "{:s} is unspecified work_in variable".format(work_in)
            )

        if algorithm == "static":
            cluster_algorithm = self._get_cluster_list_static
        elif algorithm == "dynamic":
            cluster_algorithm = self._get_cluster_list_dynamic
        else:
            raise NotImplementedError("{:s} is unspecified algorithm".format(algorithm))
        # Loop over all trajectory times
        for time in self.universe.trajectory:
            if times is not None:
                if time.time > max(times) or time.time < min(times):
                    continue
            self.cluster_list.append(cluster_algorithm())
            print("****TIME: {:8.2f}".format(time.time))
            print("---->Number of clusters {:d}".format(len(self.cluster_list[-1])))

        # Rewind Trajectory to beginning for other analysis
        self.universe.trajectory.rewind()

    def _get_cluster_list_static(self, cut_off=7.5):
        """Get Cluster from single frame with the static method
        
        This code simply loops over all atoms in the aggregate
        species and finds a cluster for each atom (all neighbours).
        This cluster is merged into the already found clusters.

        Parameters
        ----------
        cut_off : float, optional
            Radius around which to search for neighbours 

        Returns
        -------
        cluster_list : list of ResGroups or AtomGroups
        """
        cluster_list = []
        if self.search_level == "R":
            aggregate_species_atoms = self.aggregate_species.groupby("resids").values()
        elif self.search_level == "A":
            aggregate_species_atoms = self.aggregate_species

        for atoms in aggregate_species_atoms:
            cluster_temp = set(
                self.neighbour_search.search(
                    atoms=atoms, radius=cut_off, level=self.search_level
                )
            )

            cluster_list = self._merge_cluster(cluster_list, cluster_temp)

        return cluster_list

    def _merge_cluster(self, cluster_list, cluster_temp):
        """Code to merge a cluster into a cluster list
        
        This code merges a cluster into a clusterlist by reverse
        looping over the cluster list. Whenever an overlap is detected
        the new, temporary, cluster is merged into the old one and
        the new one is deleted. At the same time the temporary cluster
        is updated to be the old one merged with the new one to
        further look for overlap.

        Parameters
        ----------
        cluster_list : list of sets of clusterids
            All the sets of clusters already present.
        cluster_temp : set of clusterids
            Last found cluster, to be merged into the cluster_list

        Returns
        -------
        cluster_list : list of sets of clusterids
            Updated cluster_list

        """
        cluster_list.append(cluster_temp)
        merged_index = []

        # Loop through cluster_list in reverse with the actual also
        # the revesed indices
        for i, cluster in reversed(list(enumerate(cluster_list))):
            # If there is an intersection start merging. There is
            # always an intersection with the first cluster (identical)
            if bool(cluster.intersection(cluster_temp)):
                cluster_temp = cluster_temp | cluster  # Updating cluster_temp
                cluster_list[i] = cluster_temp
                merged_index.append(i)
                # If the cluster is not completely new there will be a
                # second intersection and we delete the previous cluster
                # Note that len(merged_index) goes back to 1 afterwards
                # and cluster_temp is the new merged cluster
                if len(merged_index) > 1.5:
                    del cluster_list[merged_index[0]]
                    del merged_index[0]
                elif len(merged_index) > 1.5:
                    warnings.warn("Wrong behaviour in cluster merge", UserWarning)

        return cluster_list

    def _get_cluster_list_dynamic(self, cut_off=7.5):
        """Get Cluster from single frame with dynamic algorithm

        Faster algorithm to find clusters. We single out one
        molecule or atom and find all its neighbours, then we call the same
        function again and find the neighbours neighbours,
        while excluding already found neighbours. We do this until
        we cant find any more neighbours. Then we choose another
        molecule or atom until we do not have any molecules/atoms left.

        Parameters
        ----------
        cut_off : float, optional
            Radius around which to search for neighbours

        Returns
        -------
        cluster_list : list of ResGroups or AtomGroups

        """
        cluster_list = []

        if self.search_level == "R":
            aggregate_species = self.aggregate_species.residues
        elif self.search_level == "A":
            aggregate_species = self.aggregate_species

        # Loop until all molecules have been in clusters
        while len(aggregate_species) > 0:
            # Initialize the search_set and temporary cluster with
            # one molecule or atom
            if self.search_level == "R":
                species_temp = aggregate_species[0].atoms.residues
            elif self.search_level == "A":
                species_temp = MDAnalysis.core.groups.AtomGroup([aggregate_species[0]])
            search_set = species_temp
            cluster_temp = species_temp
            # In this loop search set gets updated to only have new
            # neighours and cluster_temp grows
            while len(search_set) > 0:
                search_set, cluster_temp = self._grow_cluster(
                    cut_off, search_set, cluster_temp
                )
            # Once no more neighbours are found add the cluster to
            # the list and subtract the cluster from the aggregate
            # species.
            # Possible Improvement: Update NeighbourSearch object
            cluster_list.append(cluster_temp)
            aggregate_species = aggregate_species.difference(cluster_temp)

        return cluster_list

    def _grow_cluster(self, cut_off, search_set, cluster_temp):
        """Code to grow a cluster (cluster_temp) and obtain new search set
        (search_set)

        This algorithm looks for neighbours of atoms in search_set
        and adds them to the temporary cluster. The search_set
        is updated to only include newly found neighbours not
        already present in search_set. The neighbours searching
        still looks in all the atoms present in the aggregate_species.

        Parameters
        ----------
        cut_off : float, optional
            Radius around which to search for neighbours
        search_set : MDAnalysis ResidueGroup
            Atoms for which to look for neighbours
        cluster_temp : MDAanalysis ResidueGroup
            All the atoms/residues currently in the cluster

        Returns
        ------- 
        search_set : MDAnalysis ResidueGroup
            Atoms for which to look for neighbours updated to be
            the latest found ones
        cluster_temp : MDAanalysis ResidueGroup
            All the atoms/residues currently in the cluster updated
            to include the latest found ones

        """

        if self.search_level == "R":
            # Find neighbours and cast into ResidueGroup
            new_cluster_species = MDAnalysis.core.groups.ResidueGroup(
                self.neighbour_search.search(
                    atoms=self._select_species(search_set.atoms, style=self.style),
                    radius=cut_off,
                    level=self.search_level,
                )
            )
        elif self.search_level == "A":
            new_cluster_species = self.neighbour_search.search(
                atoms=search_set.atoms, radius=cut_off, level=self.search_level
            )

        # The new search_set should only have atoms not already in the cluster
        search_set = new_cluster_species.difference(cluster_temp)
        # The new temporary cluster is updated
        cluster_temp = cluster_temp.union(new_cluster_species)

        return search_set, cluster_temp

    def plot_histogram(
        self,
        ax,
        frames=(0, 1, 1),
        maxbins=False,
        density=True,
        filename=None,
        *args,
        **kwargs
    ):
        """Method to plot histograms for different timeframes

        Examples
        --------
        None yet

        Note
        ----
        By passing a axis to this function, loads of things can actually
        be externally overriden to fit every need.

        Parameters
        ----------
        ax : matplotlib axis object
        frames : list of tuples, optional
            for each tuple, the corresponding frames are averaged to
            give one cluster size distribution. Give tuple as:
            (first frame, last frame, stepsize to go throug frames)
        maxbins : bool, optional
            Set to true if you want as many bins as there are monomers
            in the largest cluster
        density : bool, optional
            Whether or not to plot for absolute occurences or
            probabilities
        filename : string, optional
            If string is given, save the plot under that name. Specify
            if you want pdf, png etc..

        Returns
        -------
        ax : matplotlib axis object
        """
        # Check if the frames desired are available
        if not isinstance(frames, list):
            frames = [frames]
        cluster_list_length = len(self.cluster_list)
        maxframe = max([index[1] for index in frames])
        if maxframe > cluster_list_length:
            raise ValueError(
                "Upper Frame limit out of range, maximal frame \
                              Number is {:d}".format(
                    cluster_list_length
                )
            )

        # Get the size distribution of all frames for all frames
        masterlist = []
        for frames_i in frames:
            masterlist.append(self._get_cluster_distribution(frames_i))

        # By making as many bins as molecules in the largest cluster
        # there is a bar for each clustersize
        if maxbins is True:
            bins = max(
                [max(cluster_distribution) for cluster_distribution in masterlist]
            )
        else:
            bins = None

        ax.hist(masterlist, bins=bins, density=density, *args, **kwargs)

        ax.set_xlabel("Number of Monomers")
        if not density is True:
            ystring = "Number of Occurrences"
        else:
            ystring = "Probability"
        ax.set_ylabel(ystring)

        if filename is None:
            plt.show()
        else:
            plt.savefig(filename)

    def _get_cluster_distribution(self, frames):
        """Helper for plot_histogram to get a cluster distribution

        Parameters
        ----------
        frames : tuple of int
            first frame, last frame and stepsize

        Returns
        -------
        cluster_distribution: list of int
            All the clusterssizes in all the frames specified
        """
        cluster_distribution = []
        for frame in self.cluster_list[slice(*frames)]:
            for cluster in frame:
                cluster_distribution.append(len(cluster))

        return cluster_distribution
