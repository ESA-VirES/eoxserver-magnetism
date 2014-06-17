wget https://pypi.python.org/packages/source/p/pysqlite/pysqlite-2.6.3.tar.gz
tar xzf pysqlite-2.6.3.tar.gz
cd pysqlite-2.6.3

sed -i "/define=SQLITE_OMIT_LOAD_EXTENSION/c\#define=SQLITE_OMIT_LOAD_EXTENSION" setup.cfg
sudo python setup.py install

cd -
rm -rf pysqlite-2.6.3.tar.gz pysqlite-2.6.3/
