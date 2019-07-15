import MDAnalysis
#from MDAnalysis.core.groups import ResidueGroup
"""
ToDo:
    Make sure PBC do what we want 
    Ensure behaviour for gro files
    Add functionality to look only at certain time windows
    Evaluation 
"""

class ClusterEnsemble():
    """Takes a list (of lists) of clusters to perform analysis

    """
    
    def __init__(self, coord, traj, cluster_objects):
        self.coord = coord
        self.traj  = traj
        self.cluster_objects = cluster_objects

    def cluster_analysis(self, cut_off=7.5, style="atom", measure="b2b", algorithm="static"):
        """High level function clustering molecules together.
            
        Args:
            coord    (str): path to coordinate file. As of now tested: tpr.
            cluster_objects
                      (str): string or list of strings with names of clustered 
                             objects. If style="atom" or "COM", this is a list 
                             of particles, if style="molecule this is a molecule
                             name
                             
            traj      (str): path to trajectory file. Has to fit to coordinate
                             file. As of now tested: xtc. 
            cut_off (float): minimal distance for two particles to be in the 
                             same cluster.
            style     (str): "atom" or "molecule" 
            measure   (str): b2b (bead to bead), COM or COG(center of geometry)
            algorithm (str): "static" or "dynamic"
        Returns: 
            Not sure yet

        ToDo:
            Implement List of trajectories, which should facilitate analysis
            of replicas.
        """
        self.universe = self._get_universe()

        self.aggregate_species = self._get_aggregate_species(style=style)
        
        self.cluster_list = []

        if algorithm == "static":
            cluster_algorithm = self._get_cluster_list_static
        elif algorithm == "dynamic":
            cluster_algorithm = self._get_cluster_list_dynamic
        else:
            print("{:s} is unspecified algorithm".format(algorithm))

        for time in self.universe.trajectory:
            self.cluster_list.append(cluster_algorithm())

    def _get_universe(self):
        """Getting the universe when having or not having a trajector

        """
        if self.traj is not None:
            universe = MDAnalysis.Universe(self.coord, self.traj)
        else:
            universe = MDAnalysis.Universe(self.coord)
        
        return universe
    
    def _get_aggregate_species(self, style="atom"):
        """Getting a dictionary of the species on which we determine aggregation


        """
        # Cast cluster_objects to list if only single string is given
        # this is necessary because of differences in processing strings and 
        # list of strings
        if type(self.cluster_objects) is not list: self.cluster_objects = [ 
                                                        self.cluster_objects 
                                                        ]
        
        # If beads are choosen we look for names instead of resnames 
        if style == "atom":
            aggregate_species  = self.universe.select_atoms(
                            "name {:s}".format(" ".join(self.cluster_objects))
                            )
        if style == "molecule":
            aggregate_species  = self.universe.select_atoms(
                        "resname {:s}".format(" ".join(self.cluster_objects))
                        )
        
        return aggregate_species


    def _get_cluster_list_static(self, cut_off=7.5):
        """Get Cluster from single frame

        """  
        from MDAnalysis.lib.NeighborSearch import AtomNeighborSearch
        
        cluster_list = []
        aggregate_species_dict = self.aggregate_species.groupby("resids")
        
        for atoms in aggregate_species_dict.values():
            cluster_temp = set(AtomNeighborSearch(self.aggregate_species).search(
                                                    atoms=atoms, 
                                                    radius=cut_off, 
                                                    level="R"
                                                    ))
            
            cluster_list = self._merge_cluster(cluster_list, cluster_temp)   
            
        return cluster_list

    def _get_cluster_list_dynamic(self, cut_off=7.5):
        """Get Cluster from single frame

        """  
        from MDAnalysis.lib.NeighborSearch import AtomNeighborSearch

        cluster_list = []
        aggregate_species_dict = self.aggregate_species.groupby("resids")
        
        for atoms in aggregate_species_dict.values():
            cluster_temp = set(AtomNeighborSearch(self.aggregate_species).search(
                                                    atoms=atoms, 
                                                    radius=cut_off, 
                                                    level="R"
                                                    ))
            
            cluster_list = self._merge_cluster(cluster_list, cluster_temp)   
            
        return cluster_list

    def _merge_cluster(self, cluster_list, cluster_temp):
        """Code to merge a cluster into a cluster list

        """
        cluster_list.append(cluster_temp)
        merged_index = []
        for i, cluster in reversed(list(enumerate(cluster_list))):
            if bool(cluster.intersection(cluster_temp)):
                cluster_temp = cluster_temp | cluster
                cluster_list[i] = cluster_temp
                merged_index.append(i)
                if len(merged_index) > 1.5:
                    del cluster_list[merged_index[0]]
                    del merged_index[0]
                elif len(merged_index) > 1.5:
                    print("Somethings wrong with the cluster merging")
        
        return cluster_list

