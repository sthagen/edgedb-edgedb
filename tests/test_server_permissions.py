#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2019-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import asyncio
import json
import os
import tempfile

import edgedb

from edb.testbase import server as server_tb
from edb.testbase import http as tb


class TestServerPermissions(tb.EdgeQLTestCase, server_tb.CLITestCaseMixin):

    PARALLELISM_GRANULARITY = 'system'
    TRANSACTION_ISOLATION = False

    async def test_server_permissions_role_01(self):
        # Check that superuser has permissions

        await self.con.query('''
            CREATE SUPERUSER ROLE foo {
                SET password := 'secret';
            };
            CREATE PERMISSION default::perm_a;
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            result = await conn.query("""
                SELECT global default::perm_a;
            """)
            self.assert_data_shape(result, [True,])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP PERMISSION default::perm_a;
            ''')

    async def test_server_permissions_role_02(self):
        # Check that non-superuser has permissions

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := default::perm_a;
            };
            CREATE PERMISSION default::perm_a;
            CREATE PERMISSION default::perm_b;
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            qry = """
                SELECT [
                    global default::perm_a,
                    global default::perm_b,
                ];
            """
            result = await conn.query(qry)
            self.assert_data_shape(result, [[True, False]])

            result, _ = self.edgeql_query(
                qry,
                user='foo',
                password='secret',
            )
            self.assert_data_shape(result, [[True, False]])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP PERMISSION default::perm_a;
                DROP PERMISSION default::perm_b;
            ''')

    async def test_server_permissions_role_03(self):
        # Check that non-superuser has permissions

        await self.con.query('''
            CREATE ROLE base {
                SET password := 'secret';
                SET permissions := default::perm_a;
            };
            CREATE ROLE foo EXTENDING base {
                SET password := 'secret';
                SET permissions := default::perm_b;
            };
            CREATE PERMISSION default::perm_a;
            CREATE PERMISSION default::perm_b;
            CREATE PERMISSION default::perm_c;
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            result = await conn.query("""
                SELECT [
                    global default::perm_a,
                    global default::perm_b,
                    global default::perm_c,
                ];
            """)
            self.assert_data_shape(result, [[True, True, False,]])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP ROLE base;
                DROP PERMISSION default::perm_a;
                DROP PERMISSION default::perm_b;
                DROP PERMISSION default::perm_c;
            ''')

    async def test_server_permissions_role_04(self):
        # Check that permissions are updated for existing connections

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := default::perm_a;
            };
            CREATE PERMISSION default::perm_a;
            CREATE PERMISSION default::perm_b;
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            result = await conn.query("""
                SELECT [
                    global default::perm_a,
                    global default::perm_b,
                ];
            """)
            self.assert_data_shape(result, [[True, False,]])

            await self.con.query('''
                ALTER ROLE foo {
                    SET permissions := default::perm_b;
                };
            ''')

            result = await conn.query("""
                SELECT [
                    global default::perm_a,
                    global default::perm_b,
                ];
            """)
            self.assert_data_shape(result, [[False, True,]])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP PERMISSION default::perm_a;
                DROP PERMISSION default::perm_b;
            ''')

    async def test_server_permissions_role_05(self):
        # Check that non-superuser has permissions

        await self.con.query('''
            CREATE ROLE base {
                SET password := 'secret';
                SET permissions := default::perm_a;
            };
            CREATE ROLE foo EXTENDING base {
                SET password := 'secret';
                SET permissions := default::perm_b;
            };
            CREATE ROLE bar EXTENDING foo {
                SET password := 'secret';
            };
            CREATE PERMISSION default::perm_a;
            CREATE PERMISSION default::perm_b;
            CREATE PERMISSION default::perm_c;
        ''')

        try:
            conn = await self.connect(
                user='bar',
                password='secret',
            )

            result = await conn.query("""
                SELECT [
                    global default::perm_a,
                    global default::perm_b,
                    global default::perm_c,
                ];
            """)
            self.assert_data_shape(result, [[True, True, False,]])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE bar;
                DROP ROLE foo;
                DROP ROLE base;
                DROP PERMISSION default::perm_a;
                DROP PERMISSION default::perm_b;
                DROP PERMISSION default::perm_c;
            ''')

    async def test_server_permissions_function_01(self):
        await self.con.query('''
            CREATE PERMISSION default::perm_a;
            CREATE PERMISSION default::perm_b;
            CREATE PERMISSION default::perm_c;
            CREATE FUNCTION test1() -> int64 {
                SET required_permissions := perm_a;
                USING (1);
            };
            CREATE FUNCTION test2() -> int64 {
                SET required_permissions := {perm_a, perm_b, perm_c};
                USING (1);
            };
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := default::perm_a;
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.query('select test1()')

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'role foo does not have required permissions: '
                'default::perm_b, default::perm_c'
            ):
                await conn.query('select test2()')

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP FUNCTION test2();
                DROP FUNCTION test1();
                DROP PERMISSION default::perm_a;
                DROP PERMISSION default::perm_b;
                DROP PERMISSION default::perm_c;
                DROP ROLE foo;
            ''')

    async def test_server_permissions_access_policy_01(self):
        # Check permission access policy works
        # with superuser

        await self.con.query('''
            CREATE SUPERUSER ROLE foo {
                SET password := 'secret';
            };
            CREATE PERMISSION default::perm_a;
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
                CREATE ACCESS POLICY readable
                    ALLOW SELECT;
                CREATE ACCESS POLICY with_perm
                    ALLOW INSERT
                    USING (global default::perm_a);
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.execute("""
                INSERT Widget { n := 1 };
            """)

            result = json.loads(await conn.query_json("""
                SELECT Widget { n } ORDER BY .n;
            """))
            self.assert_data_shape(result, [{'n': 1}])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
                DROP PERMISSION default::perm_a;
            ''')

    async def test_server_permissions_access_policy_02(self):
        # Check permission access policy works
        # with non-superuser with permission

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := {
                    sys::perm::data_modification,
                    default::perm_a,
                };
            };
            CREATE PERMISSION default::perm_a;
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
                CREATE ACCESS POLICY readable
                    ALLOW SELECT;
                CREATE ACCESS POLICY with_perm
                    ALLOW INSERT
                    USING (global default::perm_a);
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.execute("""
                INSERT Widget { n := 1 };
            """)

            result = json.loads(await conn.query_json("""
                SELECT Widget { n } ORDER BY .n;
            """))
            self.assert_data_shape(result, [{'n': 1}])

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
                DROP PERMISSION default::perm_a;
            ''')

    async def test_server_permissions_access_policy_03(self):
        # Check permission access policy works
        # with non-superuser without permission

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := {
                    sys::perm::data_modification,
                };
            };
            CREATE PERMISSION default::perm_a;
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
                CREATE ACCESS POLICY readable
                    ALLOW SELECT;
                CREATE ACCESS POLICY with_perm
                    ALLOW INSERT
                    USING (global default::perm_a);
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            with self.assertRaisesRegex(
                edgedb.AccessPolicyError,
                'access policy violation on insert of default::Widget'
            ):
                await conn.execute("""
                    INSERT Widget { n := 1 };
                """)

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
                DROP PERMISSION default::perm_a;
            ''')

    async def test_server_permissions_data_modification_01(self):
        # Non-superuser without sys::perm::data_modification
        # cannot insert, update or delete

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
            };
        ''')

        await self.con.execute('INSERT Widget { n := 1 };')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute data modification queries: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    INSERT Widget { n := 2 };
                """)

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute data modification queries: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    UPDATE Widget SET { n := .n + 1 };
                """)

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute data modification queries: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    DELETE Widget;
                """)

            # Check that nothing changed
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 1},
                ],
            )

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
            ''')

    async def test_server_permissions_data_modification_02(self):
        # Non-superuser with sys::perm::data_modification
        # can insert, update or delete

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := {
                    sys::perm::data_modification,
                };
            };
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
            };
        ''')

        await self.con.execute('INSERT Widget { n := 1 };')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.execute("""
                INSERT Widget { n := 2 };
            """)
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 1},
                    {'n': 2},
                ],
            )

            await conn.execute("""
                UPDATE Widget SET { n := .n + 1 };
            """)
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 2},
                    {'n': 3},
                ],
            )

            await conn.execute("""
                DELETE Widget;
            """)
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [],
            )

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
            ''')

    async def test_server_permissions_data_modification_03(self):
        # Capabilities are refreshed when permissions are changed

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := {
                    sys::perm::data_modification,
                };
            };
            CREATE TYPE Widget {
                CREATE PROPERTY n -> int64;
            };
        ''')

        await self.con.execute('INSERT Widget { n := 1 };')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            # Starts with sys::perm::data_modification
            await conn.execute("""
                INSERT Widget { n := 2 };
            """)
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 1},
                    {'n': 2},
                ],
            )

            # Remove sys::perm::data_modification
            await self.con.execute('''
                ALTER ROLE foo {
                    SET permissions := {};
                };
            ''')

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute data modification queries: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    INSERT Widget { n := 3 };
                """)

            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 1},
                    {'n': 2},
                ],
            )

            # Re-add sys::perm::data_modification
            await self.con.execute('''
                ALTER ROLE foo {
                    SET permissions := {
                        sys::perm::data_modification,
                    };
                };
            ''')

            await conn.execute("""
                INSERT Widget { n := 4 };
            """)
            await self.assert_query_result(
                'SELECT Widget { n } ORDER BY .n;',
                [
                    {'n': 1},
                    {'n': 2},
                    {'n': 4},
                ],
            )

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
                DROP TYPE default::Widget;
            ''')

    async def test_server_permissions_session_config_01(self):
        # Non-superuser can run session config commands
        # But not certain ones

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
            CREATE MODULE custom;
            CREATE TYPE custom::Widget {
                CREATE PROPERTY n -> int64;
            };
        ''')

        await self.con.execute('INSERT custom::Widget { n := 1 };')

        conn2 = None
        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.execute('SET MODULE custom')

            result = json.loads(await conn.query_json("""
                SELECT Widget { n } ORDER BY .n;
            """))
            self.assert_data_shape(result, [{'n': 1}])

            async with self.assertRaisesRegexTx(
                edgedb.DisabledCapabilityError,
                'role foo does not have permission'
            ):
                await conn.execute('''
                    CONFIGURE SESSION SET apply_access_policies := false
                ''')

            # Try configuring with client directly
            args = self.get_connect_args(database=self.con.dbname)
            args.update(dict(
                user='foo',
                password='secret',
            ))
            conn2 = edgedb.create_async_client(**args)
            conn2a = conn2.with_config(apply_access_policies=False)
            async with self.assertRaisesRegexTx(
                edgedb.DisabledCapabilityError,
                'role foo does not have permission'
            ):
                await conn2a.query('select 1')

        finally:
            await conn.aclose()
            if conn2:
                await conn2.aclose()
            await self.con.query('''
                DROP TYPE custom::Widget;
                DROP MODULE custom;
                DROP ROLE foo;
            ''')

    async def test_server_permissions_session_config_02(self):
        # Non-superuser can run session config commands

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := cfg::perm::configure_apply_access_policies;
            };
            CREATE GLOBAL default::bar -> int64;
            CREATE TYPE T;
            INSERT T;
            ALTER TYPE T { create access policy no allow all using (false); }
        ''')

        conn2 = None
        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )
            await conn.execute('''
                set global bar := 1;
            ''')

            result = json.loads(await conn.query_json("""
                SELECT GLOBAL bar;
            """))
            self.assert_data_shape(result, [1])

            await self.assert_query_result(
                '''
                select count(T)
                ''',
                [0],
            )

            await conn.execute('''
                CONFIGURE SESSION SET apply_access_policies := false
            ''')

            await self.assert_query_result(
                '''
                select count(T)
                ''',
                [0],
            )

            # Try configuring with client directly
            args = self.get_connect_args(database=self.con.dbname)
            args.update(dict(
                user='foo',
                password='secret',
            ))
            conn2 = edgedb.create_async_client(**args)
            self.assertEqual(
                await conn2.query_single('select count(T)'),
                0,
            )

            conn2a = conn2.with_config(apply_access_policies=False)
            self.assertEqual(
                await conn2a.query_single('select count(T)'),
                1,
            )

        finally:
            await conn.aclose()
            if conn2:
                await conn2.aclose()
            await self.con.query('''
                DROP GLOBAL default::bar;
                DROP ROLE foo;
            ''')

    async def test_server_permissions_persistent_config_01(self):
        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
        ''')

        conn = await self.connect(
            user='foo',
            password='secret',
        )
        try:
            async with self.assertRaisesRegexTx(
                edgedb.DisabledCapabilityError,
                'cannot execute instance configuration commands: '
                'role foo does not have permission'
            ):
                await conn.execute('''
                    CONFIGURE INSTANCE SET apply_access_policies := false
                ''')
            async with self.assertRaisesRegexTx(
                edgedb.DisabledCapabilityError,
                'cannot execute database branch configuration commands: '
                'role foo does not have permission'
            ):
                await conn.execute('''
                    CONFIGURE CURRENT BRANCH SET apply_access_policies
                        := false
                ''')

            await self.con.query('''
                ALTER ROLE foo {
                    SET permissions := sys::perm::branch_config;
                };
            ''')

            await conn.execute('''
                CONFIGURE CURRENT BRANCH RESET apply_access_policies
            ''')

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
            ''')

    async def test_server_permissions_ddl_01(self):
        # Non-superuser cannot run ddl commands

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute DDL commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    CREATE TYPE Widget;
                """)

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
            ''')

    async def test_server_permissions_ddl_02(self):
        # Non-superuser with sys::perm::ddl can run ddl commands

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
                SET permissions := sys::perm::ddl;
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            await conn.execute("""
                CREATE TYPE Widget;
            """)

            # But *not* system wide DDL!
            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute instance-wide DDL commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    CREATE SUPERUSER ROLE bar {
                        SET password := 'secret';
                    };
                """)
            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute instance-wide DDL commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    CREATE EMPTY BRANCH bar
                """)

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP TYPE Widget;
                DROP ROLE foo;
            ''')

    async def test_server_permissions_admin_01(self):
        # Non-superuser cannot run administer, describe, and analyze commands

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
        ''')

        try:
            conn = await self.connect(
                user='foo',
                password='secret',
            )

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute ADMINISTER commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    ADMINISTER schema_repair();
                """)

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute DESCRIBE commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    DESCRIBE SCHEMA
                """)

            with self.assertRaisesRegex(
                edgedb.DisabledCapabilityError,
                'cannot execute ANALYZE commands: '
                'role foo does not have permission'
            ):
                await conn.execute("""
                    ANALYZE SELECT 1
                """)

        finally:
            await conn.aclose()
            await self.con.query('''
                DROP ROLE foo;
            ''')

    async def test_server_permissions_dump_01(self):
        # Non-superuser cannot do dumps or restores

        await self.con.query('''
            CREATE ROLE foo {
                SET password := 'secret';
            };
        ''')

        try:
            conn_args = self.get_connect_args(
                user='foo',
                password='secret',
            )
            with tempfile.TemporaryDirectory() as f:
                fname = os.path.join(f, 'dump')
                with self.assertRaisesRegex(
                    AssertionError,
                    'role foo does not have permission'
                ):
                    await asyncio.to_thread(
                        self.run_cli_on_connection,
                        conn_args,
                        '-d', self.get_database_name(), 'dump', fname
                    )

                # Do a real dump so we can check restore fails for the
                # right reason
                await asyncio.to_thread(
                    self.run_cli,
                    '-d', self.get_database_name(), 'dump', fname
                )

                with self.assertRaisesRegex(
                    AssertionError,
                    'role foo does not have permission'
                ):
                    await asyncio.to_thread(
                        self.run_cli_on_connection,
                        conn_args,
                        '-d', self.get_database_name(), 'restore', fname
                    )

        finally:
            await self.con.query('''
                DROP ROLE foo;
            ''')
