import sqlite3
# Create table
#c.execute('''CREATE TABLE stocks
#             (date text, trans text, symbol text, qty real, price real)''')

# Insert a row of data
#c.execute("INSERT INTO stocks VALUES ('2006-01-05','BUY','RHAT',100,35.14)")

# Save (commit) the changes
#conn.commit()



#t = ('RHAT',)
#c.execute('SELECT * FROM stocks WHERE symbol=?', t)
#print(c.fetchone())

# Larger example that inserts many records at a time
purchases = [('2006-03-28', 'BUY', 'IBM', 1000, 45.00),
             ('2006-04-05', 'BUY', 'MSFT', 1000, 72.00),
             ('2006-04-06', 'SELL', 'IBM', 500, 53.00),
            ]
#c.executemany('INSERT INTO stocks VALUES (?,?,?,?,?)', purchases)
#conn.commit
if __name__ == '__main__':
    conn = sqlite3.connect('abbot.sqlite3')

    c = conn.cursor()

    for row in c.execute('SELECT * FROM usage_commands ORDER BY server, user, channel, command_name'):
        print(row)

    # We can also close the connection if we are done with it.
    # Just be sure any changes have been committed or they will be lost.
    conn.close()