 import shutil                                                                                                    │ │
 import os                                                                                                        │ │
                                                                                                                  │ │
 def zip_folder(folder_path, output_path=None):                                                                   │ │
     """                                                                                                      
     Zip a folder using shutil, prioritizing speed over compression.                                          
                                                                                                              
     Args:                                                                                                    
         folder_path (str): Path to the folder to zip                                                         
         output_path (str, optional): Output zip file path. If None, uses folder name + .zip                  
                                                                                                              
     Returns:  
         str: Path to the created zip file   
     """   
     if not os.path.exists(folder_path): 
         raise FileNotFoundError(f"Folder not found: {folder_path}")
     if not os.path.isdir(folder_path): 
         raise ValueError(f"Path is not a directory: {folder_path}")
     if output_path is None:  
         output_path = f"{folder_path}.zip"  
     # Remove .zip extension if present to avoid double extension   
     if output_path.endswith('.zip'):
         base_name = output_path[:-4]  
     else:  
         base_name = output_path

     # Use shutil.make_archive with zip format and no compression for speed                                   
     zip_path = shutil.make_archive(
         base_name=base_name,
         format='zip',
         root_dir=os.path.dirname(folder_path),
         base_dir=os.path.basename(folder_path)
     )
     return zip_path