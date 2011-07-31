'''
Created on 04/08/2010

@author: piranna
'''

import stat

from os      import listdir
from os.path import join, splitext

from multiprocessing import Lock


class DictObj(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        try:
            self[name] = value
        except KeyError:
            raise AttributeError(name)


def DictObj_factory(cursor, row):
    d = DictObj()
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class DB():
    '''
    classdocs
    '''

    def __init__(self, connection, drive, sector_size):                     # OK
        '''
        Constructor
        '''
        self.connection = connection

        self.connection.row_factory = DictObj_factory
        self.connection.isolation_level = None

        # Store data in UNIX timestamp instead ISO format (sqlite default)
        import datetime, time
        import sqlite3
        def adapt_datetime(ts):
            return time.mktime(ts.timetuple())
        sqlite3.register_adapter(datetime.datetime, adapt_datetime)

        # SQLite tune-ups
        self.connection.execute("PRAGMA synchronous = OFF;")
        self.connection.execute("PRAGMA temp_store = MEMORY;")  # Not so much

        # Force enable foreign keys check
        self.connection.execute("PRAGMA foreign_keys = ON;")

        self._lock = Lock()

        def Get_NumSectors():
            # http://stackoverflow.com/questions/283707/size-of-an-open-file-object
            drive.seek(0, 2)
            end = drive.tell()
            drive.seek(0)
            return (end - 1) // sector_size

        self.__sector_size = sector_size

        self.__queries = self.__LoadQueries('/home/piranna/Proyectos/FUSE/PirannaFS/src/sql')
        self.__Create_Database(Get_NumSectors())


    def getinfo(self, parent_dir, name):                                    # OK
        '''
        Get the stat info of a directory entry
        '''
#        with self._lock:
        with self.connection:
            inodeCreation = self.__Get_InodeCreation(parent_dir, name)
            if inodeCreation:
                return self.connection.execute(self.__queries['getinfo'],
                                               inodeCreation).fetchone()


    def link(self, parent_dir, name, child_entry):                          # OK
#        print >> sys.stderr, '*** link', parent_dir,name,child_entry

        cursor = self.connection.cursor()
        cursor.execute(self.__queries['link'],
            {"parent_dir":parent_dir, "name":name, "child_entry":child_entry})

        return cursor.lastrowid


    def mkdir(self):                                                        # OK
        '''
        Make a new directory
        '''
#        with self._lock:
        with self.connection:
            inode = self.__Make_DirEntry(stat.S_IFDIR)
            self.connection.execute(self.__queries['dir.make'],
                {"inode":inode})

        return inode


    def mknod(self):                                                        # OK
        '''
        Make a new file
        '''
#        with self._lock:
        with self.connection:
            inode = self.__Make_DirEntry(stat.S_IFREG)
            self.connection.execute(self.__queries['mknod'],
                {"inode":inode})

        return inode


    def readdir(self, parent, limit= -1):                                   # OK
        query = self.connection.execute(self.__queries['dir.read'],
                                        {"parent_dir":parent, "limit":limit})
        return query.fetchall()


    def rename(self, parent_old, name_old, parent_new, name_new):           # OK
        return self.connection.execute(self.__queries['rename'],
            {"parent_new":parent_new, "name_new":name_new,
             "parent_old":parent_old, "name_old":name_old})


    def unlink(self, parent_dir_inode, name):                               # OK
        return self.connection.execute(self.__queries['unlink'],
            {"parent_dir":parent_dir_inode, "name":name})


    def utimens(self, inode, ts_acc, ts_mod):
        if ts_acc == None: ts_acc = "now"
        if ts_mod == None: ts_mod = "now"

        return self.connection.execute(self.__queries['utimens'],
            {"access":ts_acc, "modification":ts_mod, "inode":inode})


    def Free_Chunks(self, chunk):
        """Free chunks whose offset is greather that new file size"""
        return self.connection.execute(self.__queries['Free_Chunks'], chunk)


    def Get_Chunks(self, file, floor, ceil):                                # OK
        '''
        Get chunks of the required file that are content between the
        defined floor and ceil
        '''
        result = self.connection.execute(self.__queries['Get_Chunks'],
                                         {"ceil": ceil,
                                          "file": file,
                                          "floor":floor})
        return result.fetchall()


    def Get_Chunks_Truncate(self, file, ceil):
        """
        Get chunks whose block+length is greather that new file size
        """
        return self.connection.execute(self.__queries['Get_Chunks_Truncate'],
            {"ceil":ceil, "file":file})


    def Get_FreeChunk_BestFit(self, sectors_required, blocks):              # OK
        '''Get the free chunk that best fit to the requested space.

        'Best fit' here means that it's the smallest free chunk whose size is
        equals-or-bigger or it's the biggest one that is smaller
        that the requested size
        '''
        result = self.connection.execute(self.__queries['Get_FreeChunk_BestFit'],
            {"blocks":','.join([str(block) for block in blocks]),
             "sectors_required":sectors_required})
        return result.fetchone()


    def Get_FreeSpace(self):
        """Get the free space available in the filesystem"""
        result = self.connection.execute(self.__queries['Get_FreeSpace']).fetchone()
        if result:
            return result['size'] * self.__sector_size
        return 0


    def Get_Inode(self, parent_dir, name):                                  # OK
        '''
        Get the inode of a dir entry
        from a given parent directory inode and a dir entry name
        '''
        inode = self.__Get_InodeCreation(parent_dir, name)
        if inode:
            return inode['inode']


    def Get_Mode(self, inode):                                              # OK
        '''
        Get the mode of a file
        from a given file inode
        '''
        result = self.connection.execute(self.__queries['Get_Mode'],
                                         {"inode":inode})
        result = result.fetchone()

        if result:
            return result['type']


    def Get_Size(self, inode):                                              # OK
        '''
        Get the size of a file
        from a given file inode
        '''
        result = self.connection.execute(self.__queries['Get_Size'],
                                         {"inode":inode})
        result = result.fetchone()

        if result:
            return result['size']


    def __Make_DirEntry(self, type):                                          # OK
        '''
        Make a new dir entry
        and return its inode
        '''
        cursor = self.connection.cursor()
        cursor.execute(self.__queries['__Make_DirEntry'],
                       {"type":type})

        return cursor.lastrowid


    def Put_Chunks(self, chunks):                                           # OK
        return self.connection.executemany(self.__queries['Put_Chunks'], chunks)


    def Set_Size(self, inode, length):                                      # OK
        return self.connection.execute(self.__queries['Set_Size'],
                                       {"size":length, "inode":inode})


    def Split_Chunks(self, chunk):                                          # OK
        """
        Split the chunks in the database in two (old-head and new-tail)
        based on it's defined length
        """
        def ChunkConverted():
            """[Hack] None objects get stringed to 'None' while SQLite queries
            expect 'NULL' instead. This function return a newly dict with
            all None objects converted to 'NULL' valued strings.
            """
            d = {}
            for key, value in chunk.iteritems():
                d[key] = "NULL" if value == None else value
            return d

        # Create new chunks containing the tail sectors and
        # update the old chunks length to contain only the head sectors
        sql = self.__queries['Split_Chunks'] % ChunkConverted()
        self.connection.executescript(sql)


    def __Create_Database(self, num_sectors, first_sector=0):               # OK
#        with self._lock:
        with self.connection:
            self.connection.executescript(self.__queries['__Create_Database_1'])

            # If directories table is empty (table has just been created)
            # create initial row defining the root directory
            if not self.connection.execute('SELECT * FROM dir_entries LIMIT 1').fetchone():
                sql = (self.__queries['__Create_Database_2']
                       % {"type":stat.S_IFDIR})
                self.connection.executescript(sql)

            # If chunks table is empty (table has just been created)
            # create initial row defining all the partition as free
            if not self.connection.execute('SELECT * FROM chunks LIMIT 1').fetchone():
    #            self.connection.execute("PRAGMA foreign_keys = OFF")
                self.connection.execute(self.__queries['__Create_Database_3'],
                                        {"length":num_sectors,
                                         "sector":first_sector})
    #            self.connection.execute("PRAGMA foreign_keys = ON")


    def __Get_InodeCreation(self, parent_dir, name):                        # OK
        '''
        Get the inode and the creation date of a dir entry
        from a given parent directory inode and a dir entry name
        '''
        result = self.connection.execute(self.__queries['__Get_InodeCreation'],
                                         {"parent_dir":parent_dir,
                                          "name":unicode(name)})
        return result.fetchone()


    def __LoadQueries(self, dirPath):
        result = {}

        for filename in listdir(dirPath):
            with open(join(dirPath, filename)) as f:
                result[splitext(filename)[0]] = f.read()

        return result