'''
Created on 20/09/2010

@author: piranna
'''

import errno,stat,sys

import plugins



class symlinks(plugins.Plugin):
    def __init__(self):
        self.__db = None

        plugins.connect(self.create,"FS.__init__")
        plugins.connect(self.symlink,"FS.symlink")
        plugins.connect(self.readlink,"FS.readlink")


    def create(self, db):
        '''
        Create the log table in the database
        '''
#        print >> sys.stderr, '*** create', db

        self.__db = db
        self.__db.connection.execute('''
            CREATE TABLE IF NOT EXISTS symlinks
            (
                inode  INTEGER PRIMARY KEY,

                target TEXT    NOT NULL,

                FOREIGN KEY(inode) REFERENCES dir_entries(inode)
                    ON DELETE CASCADE ON UPDATE CASCADE
            )
        ''')


    def readlink(self, sender, path):
        '''
        Read a symlink to a file
        '''
#        print >> sys.stderr, '*** fs_readlink', sender,path

        if not path:
            return -errno.ENOENT

        inode = sender.Get_Inode(path[1:])
        if inode < 0:
            return inode

        # Read symlink
        target = self.__db.connection.execute('''
            SELECT target FROM symlinks
            WHERE inode=?
            ''',
            (inode,)).fetchone()
#        print >> sys.stderr, "\t", target

        if target:
            return str(target['target'])

        return -errno.EINVAL


    def symlink(self, sender, targetPath,linkPath):
        '''
        Make a symlink to a file
        symlink is only called if there isn't already another object
        with the requested linkname
        '''
#        print >> sys.stderr, '*** symlink', targetPath,linkPath

        # If no linkPath,
        # return error
        if not linkPath:
            return -errno.ENOENT

        # Get parent dir of linkPath
        inodeName = sender.Path2InodeName(linkPath[1:])
        if inodeName < 0:
            return inodeName
        link_parentInode,name = inodeName

        # Check if exist a file, dir or symlink with the same name in this dir
        if sender.Get_Inode(name, link_parentInode) >= 0:
            return -errno.EEXIST

        # Make symlink
        inode = self.__db.Make_DirEntry(stat.S_IFLNK)
        self.__db.connection.execute('''
            INSERT INTO symlinks(inode,target)
            VALUES(?,?)
            ''',
            (inode,targetPath))

        self.__db.link(link_parentInode,name,inode)

        # Return success
        return 0



if __name__ == '__main__':
    import unittest

    class Test(unittest.TestCase):
        pass

    unittest.main()