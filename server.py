from flask import Flask, render_template, url_for, current_app, redirect, request, flash, session
from passlib.hash import pbkdf2_sha256 as hasher
import psycopg2 as dbapi2
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super secret key"
dsn = os.getenv("DATABASE_URL")


def main_page():
    if request.method == "GET":
        return render_template("main.html")
    else:
        e_mail = request.form["e-mail"]
        password = request.form["password"]
        statement = """SELECT * FROM USERS WHERE (E_MAIL = %s) """
        try:
            success = False
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            cursor.execute(statement, (e_mail, ))
            user = cursor.fetchall()
            if len(user) != 0:
                success = True
            connection.commit()
            cursor.close()
            if success:
                correct_pass = hasher.verify(password,user[0][2])
                if correct_pass:
                    session['username'] = user[0][1]
                    return redirect(url_for('dashboard_page', user_name=user[0][1], user_type=user[0][4]))
                else:
                    flash("password is incorrect.", "error")
                    return redirect(url_for('main_page'))
            else:
                flash("E-mail or password is incorrect.", "error")
                return redirect(url_for('main_page'))
        except dbapi2.DatabaseError:
            flash("An error occured.", "error")
            connection.rollback()
            return redirect(url_for('main_page'))
        finally:
            connection.close()


def dashboard_page(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        tot_cus = 0
        tot_oil = 0
        tot_edg = 0
        tot_dark = 0
        tot_light = 0
        tot_yield = 0
        avg_yield = 0
        if user_type == 'HQ':
            stats = []
            statement_1 = """SELECT COUNT(ID),SUM(OILED_KG), SUM(LIGHT_KG), SUM(DARK_KG), SUM(EDGED_KG),
                             AVG((OILED_KG * OILED_YIELD + DARK_KG * DARK_YIELD + LIGHT_KG * LIGHT_YIELD + EDGED_KG* EDGED_YIELD)
                                / (OILED_KG+DARK_KG+LIGHT_KG+EDGED_KG))
                             FROM DEPOSITS WHERE (HQ_ID = (SELECT ID FROM USERS WHERE USERNAME = %s)) """  # deposit_stats
            statement_2 = """SELECT COUNT(BRANCHES.USER_ID)
                             FROM (SELECT CHILD_ID FROM RELATIONS WHERE (PARENT_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))) AS A
							 JOIN BRANCHES ON A.CHILD_ID = BRANCHES.USER_ID """  # branch count
            statement_3 = "SELECT AVG(OILED) FROM PRICES WHERE (HQ_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))"
            statement_4 = """SELECT FULL_NAME,COUNT(CUSTOMER_ID) , SUM(OILED_KG), SUM(DARK_KG), SUM(LIGHT_KG), SUM(EDGED_KG),
                            AVG(OILED_YIELD), AVG(DARK_YIELD), AVG(LIGHT_YIELD), AVG(EDGED_YIELD), USER_ID from
                             (select user_id, full_name from branches inner join relations on branches.user_id = relations.child_id
                             where relations.parent_ID = (SELECT ID FROM USERS WHERE USERNAME = %s) ) as a left join deposits on a.user_id = deposits.branch_id
                             group by full_name, USER_ID """
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (user_name,))
                stats.append(cursor.fetchone())  # stats[0] -> deposit_stats
                cursor.execute(statement_2, (user_name,))
                stats.append(cursor.fetchone())   # stats[1][0] -> branch count
                cursor.execute(statement_3, (user_name,))
                # stats[2] -> avg oiled hazelnut price
                stats.append(cursor.fetchone())
                cursor.execute(statement_4, (user_name,)) # stats[3] -> best branch name
                temp = cursor.fetchall()
                if len(temp) == 0:
                    stats.append("There is no active Branch.")
                else:
                    max_cus = 0
                    name = "All branches have 0 customer."
                    for row in temp:
                        if row[1] > max_cus:
                            max_cus = row[1]
                            name = row[0]
                    stats.append(name)
                connection.commit()
                cursor.close()
            except dbapi2.DatabaseError:
                connection.rollback()
                flash("HQ stats cannot be gotten from database", "error")
            finally:
                connection.close()
                return render_template("HQ_dashboard.html", stats=stats, user_name=user_name, user_type=user_type)

        elif user_type == 'branch':
            stats = []
            statement_1 = """SELECT COUNT(ID),SUM(OILED_KG), SUM(LIGHT_KG), SUM(DARK_KG), SUM(EDGED_KG),
                             AVG((OILED_KG * OILED_YIELD + DARK_KG * DARK_YIELD + LIGHT_KG * LIGHT_YIELD + EDGED_KG* EDGED_YIELD)
                                / (OILED_KG+DARK_KG+LIGHT_KG+EDGED_KG+10E-6))
                             FROM DEPOSITS WHERE (BRANCH_ID = (SELECT ID FROM USERS WHERE USERNAME = %s)) """  # deposit_stats
            statement_3 = "SELECT AVG(OILED),AVG(LIGHT),AVG(DARK) FROM PRICES WHERE (BRANCH_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))"
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (user_name,))
                stats.append(cursor.fetchone())  # stats[0] -> deposit_stats
                # cursor.execute(statement_2, (user_name,))
                # stats.append( cursor.fetchone() )   # stats[1][0] -> branch count
                cursor.execute(statement_3, (user_name,))

                # stats[1] -> hazelnut prices
                stats.append(cursor.fetchone())
                connection.commit()
                cursor.close()
            except dbapi2.DatabaseError:
                connection.rollback()
                flash("Branch stats cannot be gotten from database", "error")
            finally:
                connection.close()
                return render_template("branch_dashboard.html", stats=stats, user_name=user_name, user_type=user_type)
        elif user_type == 'customer':
            statement_1 = """ SELECT * FROM DEPOSITS WHERE (CUSTOMER_ID = (SELECT ID FROM USERS WHERE(USERNAME = %s))) """
            statement_2 = """ SELECT * FROM TRANSACTIONS WHERE (DEPOSIT_ID = (SELECT ID FROM
                          DEPOSITS WHERE(CUSTOMER_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))))"""
            statement_3 = """SELECT PRICES.OILED, PRICES.DARK, PRICES.LIGHT, PRICES.EDGED
                             FROM (SELECT * FROM RELATIONS WHERE (CHILD_ID = (SELECT ID FROM USERS WHERE(USERNAME = %s)))) AS A
                             JOIN PRICES ON A.PARENT_ID=PRICES.BRANCH_ID"""
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (user_name,))
                stats = cursor.fetchone()
                cursor.execute(statement_2, (user_name,))
                transactions = cursor.fetchall()
                cursor.execute(statement_3, (user_name,))
                price = cursor.fetchone()
                connection.commit()
                cursor.close()
            except dbapi2.DatabaseError:
                connection.rollback()
                flash("Cannot get customer hazelnut datas.", "error")
            finally:
                connection.close()
                return render_template("customer_dashboard.html", stats=stats, transactions=transactions,
                                        price=price, user_name=user_name, user_type=user_type)
        else:
            return render_template("main.html")
    else:  # dashboard with post method is only valid for customer dashboard
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        form_oiled_kg = request.form["oiled_kg"]
        form_dark_kg = request.form["dark_kg"]
        form_light_kg = request.form["light_kg"]
        form_edged_kg = request.form["edged_kg"]
        statement_1 = """ SELECT * FROM DEPOSITS WHERE (CUSTOMER_ID = (SELECT ID FROM USERS WHERE(USERNAME = %s))) """
        statement_2 = """ SELECT * FROM TRANSACTIONS WHERE (DEPOSIT_ID = (SELECT ID FROM
                          DEPOSITS WHERE(CUSTOMER_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))))"""
        statement_3 = """SELECT PRICES.OILED, PRICES.DARK, PRICES.LIGHT, PRICES.EDGED
                         FROM (SELECT * FROM RELATIONS WHERE (CHILD_ID = (SELECT ID FROM USERS WHERE(USERNAME = %s)))) AS A
                         JOIN PRICES ON A.PARENT_ID=PRICES.BRANCH_ID"""
        statement_4 = """ UPDATE DEPOSITS SET OILED_KG = %s, DARK_KG = %s, LIGHT_KG = %s, EDGED_KG = %s
                          WHERE (CUSTOMER_ID = (SELECT ID FROM USERS WHERE(USERNAME = %s)))"""
        statement_5 = """ INSERT INTO TRANSACTIONS (DEPOSIT_ID,DATE,PRICE,OILED,DARK,LIGHT,EDGED) VALUES ((SELECT ID FROM
                          DEPOSITS WHERE ( CUSTOMER_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))),%s,%s,%s,%s,%s,%s) """
        try:
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            cursor.execute(statement_3, (user_name,))
            price = cursor.fetchone()
            cursor.execute(statement_1, (user_name,))
            stats = cursor.fetchone()
            tot_price = int(form_oiled_kg) * float(price[0]) * (float(stats[5]) / 50.0) + int(form_dark_kg) * (float(stats[7]) / 50.0) * float(
                price[1]) + int(form_light_kg) * float(price[2]) * (float(stats[9]) / 50.0) + int(form_edged_kg) * float(price[3]) * (float(stats[11]) / 50.0)
            if len(stats) != 0:
                oiled_ = int(stats[4])-int(form_oiled_kg)
                dark_ = int(stats[6])-int(form_dark_kg)
                light_ = int(stats[8])-int(form_light_kg)
                edged_ = int(stats[10])-int(form_edged_kg)
                cursor.execute(statement_4, (oiled_, dark_,
                               light_, edged_, user_name))
                cursor.execute(statement_5, (user_name, date, tot_price,
                               form_oiled_kg, form_dark_kg, form_light_kg, form_edged_kg))
                cursor.execute(statement_1, (user_name,))
                stats = cursor.fetchone()
                cursor.execute(statement_2, (user_name,))
                transactions = cursor.fetchall()
                if int(form_oiled_kg) == 0 and int(form_dark_kg) == 0 and int(form_light_kg) == 0 and int(form_edged_kg) == 0:
                    flash(
                        "You cannot make transactions without sell anything.", "error")
                    connection.rollback()
                    cursor.execute(statement_2, (user_name,))
                    transactions = cursor.fetchall()
                    connection.close()
                    return render_template("customer_dashboard.html", stats=stats, transactions=transactions,
                                    price=price, user_name=user_name, user_type=user_type)
                connection.commit()
                cursor.close()
                flash("You have sold your nuts successfully.", "success")
            else:
                flash("ERROR!", "error")
        except dbapi2.DatabaseError:
            flash("Error occured when processing transaction.", "error")
            connection.rollback()
        finally:
            connection.close()
            return render_template("customer_dashboard.html", stats=stats, transactions=transactions,
                                    price=price, user_name=user_name, user_type=user_type)


def add_customer(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        return render_template("add_customer.html", user_name=user_name, user_type=user_type)
    else:
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        form_name = request.form["full_name"]
        form_oiled_kg = request.form["oiled_kg"]
        form_oiled_yield = request.form["oiled_yield"]
        form_light_kg = request.form["light_kg"]
        form_light_yield = request.form["light_yield"]
        form_edged_kg = request.form["edged_kg"]
        form_edged_yield = request.form["edged_yield"]
        form_dark_kg = request.form["dark_kg"]
        form_dark_yield = request.form["dark_yield"]
        form_cus_mail = request.form["cus_email"]
        form_cus_pass = request.form["cus_pass"]
        hashed_password = hasher.hash(form_cus_pass)
        form_conf_cus_pass = request.form["conf_cus_pass"]
        statement_1 = """ INSERT INTO USERS (USERNAME,PASSWORD,E_MAIL,TYPE) VALUES (%s,%s,%s,'customer')"""
        statement_2 = """ INSERT INTO CUSTOMERS (USER_ID,FULL_NAME) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),%s)"""
        statement_3 = """ INSERT INTO RELATIONS (CHILD_ID,PARENT_ID) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),(SELECT ID FROM USERS WHERE USERNAME = %s))"""
        statement_4 = """ INSERT INTO RELATIONS (CHILD_ID,PARENT_ID) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),(SELECT PARENT_ID FROM RELATIONS WHERE CHILD_ID =
                          (SELECT ID FROM USERS WHERE USERNAME = %s)))"""
        statement_5 = """ INSERT INTO DEPOSITS (CUSTOMER_ID,BRANCH_ID,HQ_ID,OILED_KG,OILED_YIELD,DARK_KG,DARK_YIELD,
                          LIGHT_KG,LIGHT_YIELD,EDGED_KG,EDGED_YIELD)
                          VALUES ((SELECT ID FROM USERS WHERE USERNAME = %s),(SELECT ID FROM USERS WHERE USERNAME = %s),
                          (SELECT PARENT_ID FROM RELATIONS WHERE CHILD_ID =(SELECT ID FROM USERS WHERE USERNAME = %s)),
                          %s,%s,%s,%s,%s,%s,%s,%s)"""
        statement_6 = """ INSERT INTO TRANSACTIONS (DEPOSIT_ID,DATE,PRICE,OILED,DARK,LIGHT,EDGED) VALUES ((SELECT ID FROM
                          DEPOSITS WHERE ( CUSTOMER_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))),%s,0,%s,%s,%s,%s) """
        if form_cus_pass != form_conf_cus_pass:
            flash("Passwords are not matching.", "error")
            return redirect(url_for('add_customer', user_name=user_name, user_type=user_type))
    try:
        connection = dbapi2.connect(dsn)
        cursor = connection.cursor()
        cursor.execute(statement_1, (form_name, hashed_password, form_cus_mail))
        cursor.execute(statement_2, (form_name, form_name))
        cursor.execute(statement_3, (form_name, user_name))
        cursor.execute(statement_4, (form_name, user_name))
        cursor.execute(statement_5, (form_name, user_name, user_name, form_oiled_kg, form_oiled_yield, form_dark_kg,
        form_dark_yield, form_light_kg, form_light_yield, form_edged_kg, form_edged_yield))
        cursor.execute(statement_6, (form_name, date, form_oiled_kg,
                       form_dark_kg, form_light_kg, form_edged_kg))
        connection.commit()
        cursor.close()
        flash("Customer has been added succesfully.", "success")
    except dbapi2.DatabaseError:
        connection.rollback()
        flash("Customer could not be added.", "error")
    finally:
        connection.close()
        return redirect(url_for('add_customer', user_name=user_name, user_type=user_type))


def find_customer(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        statement_1 = """SELECT * FROM (SELECT CHILD_ID FROM RELATIONS
			             WHERE (PARENT_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))) AS A
			             JOIN CUSTOMERS ON A.CHILD_ID = CUSTOMERS.USER_ID
                         FETCH FIRST 10 ROWS ONLY"""
        try:
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            cursor.execute(statement_1, (user_name, ))
            customer_data = cursor.fetchall()
            connection.commit()
            cursor.close()
        except dbapi2.DatabaseError:
            connection.rollback()
            flash("Customers cannot be fetched from database.", "error")
        finally:
            connection.close()
            return render_template("find_customer.html", user_name=user_name, user_type=user_type, data=customer_data)
    else:
        form_submit = request.form["submit"]
        if form_submit == "id":
            form_id = int(request.form["id"])
            statement_1 = """SELECT * FROM (SELECT * FROM (SELECT CHILD_ID FROM RELATIONS
			             WHERE (PARENT_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))) AS A
			             JOIN CUSTOMERS ON A.CHILD_ID = CUSTOMERS.USER_ID) AS B
                         WHERE (CHILD_ID = %s) """
        else:
            form_name = request.form["full_name"]
            statement_1 = """SELECT * FROM(SELECT * FROM (SELECT CHILD_ID FROM RELATIONS
			             WHERE (PARENT_ID = (SELECT ID FROM USERS WHERE USERNAME = %s))) AS A
			             JOIN CUSTOMERS ON A.CHILD_ID = CUSTOMERS.USER_ID) AS B
                         WHERE (FULL_NAME LIKE %s) """
        try:
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            if form_submit == "id":
                cursor.execute(statement_1, (user_name, form_id))
            else:
                form_name = form_name + "%"
                cursor.execute(statement_1, (user_name, form_name))
            customer_data = cursor.fetchall()
            connection.commit()
            cursor.close()
        except dbapi2.DatabaseError:
            connection.rollback()
            flash("Customers cannot be fetched from database.", "error")
        finally:
            connection.close()
            return render_template("find_customer.html", user_name=user_name, user_type=user_type, data=customer_data)


def add_branch(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        return render_template("add_branch.html", user_name=user_name, user_type=user_type)
    else:
        form_br_name = request.form["branch_name"]
        form_br_mail = request.form["br_email"]
        form_br_pass = request.form["br_pass"]
        hashed_password = hasher.hash(form_br_pass)
        form_conf_br_pass = request.form["conf_br_pass"]
        statement_1 = """ INSERT INTO USERS (USERNAME,PASSWORD,E_MAIL,TYPE) VALUES (%s,%s,%s,'branch')"""
        statement_2 = """ INSERT INTO BRANCHES (USER_ID,FULL_NAME) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),%s)"""
        statement_3 = """ INSERT INTO RELATIONS (CHILD_ID,PARENT_ID) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),(SELECT ID FROM USERS WHERE USERNAME = %s))"""
        statement_4 = """ INSERT INTO PRICES (HQ_ID,BRANCH_ID,OILED,DARK,LIGHT,EDGED)
                          VALUES ((SELECT ID FROM USERS WHERE USERNAME = %s),(SELECT ID FROM USERS WHERE USERNAME = %s),
                          20,20,20,20)"""
        if form_br_pass != form_conf_br_pass:
            flash("Passwords are not matching.", "error")
            return redirect(url_for('add_branch', user_name=user_name, user_type=user_type))
    try:
        connection = dbapi2.connect(dsn)
        cursor = connection.cursor()
        cursor.execute(statement_1, (form_br_name, hashed_password, form_br_mail))
        cursor.execute(statement_2, (form_br_name, form_br_name))
        cursor.execute(statement_3, (form_br_name, user_name))
        cursor.execute(statement_4, (user_name, form_br_name))
        connection.commit()
        cursor.close()
        flash("Branch has been added succesfully.", "success")
    except dbapi2.DatabaseError:
        connection.rollback()
        flash("Branch could not be added", "error")
    finally:
        connection.close()
        return redirect(url_for('add_branch', user_name=user_name, user_type=user_type))


def create_account():
    if request.method == "GET":
        return render_template("create_account.html")
    else:
        form_company_name = request.form["company_name"]
        form_username = request.form["username"]
        form_password = request.form["password"]
        hashed_password = hasher.hash(form_password)
        form_password_conf = request.form["password_conf"]
        form_e_mail = request.form["e-mail"]
        statement_1 = """ INSERT INTO USERS (USERNAME,PASSWORD,E_MAIL,TYPE) VALUES (%s,%s,%s,'HQ')"""
        statement_2 = """ INSERT INTO HEADQUARTERS (USER_ID,FULL_NAME) VALUES ((SELECT ID FROM
                          USERS WHERE USERNAME = %s),%s)"""
        if form_password != form_password_conf:
            flash("Passwords are not matching.", "error")
            return redirect(url_for('create_account'))
    try:
        connection = dbapi2.connect(dsn)
        cursor = connection.cursor()
        cursor.execute(statement_1, (form_username,
                       hashed_password, form_e_mail))
        cursor.execute(statement_2, (form_username, form_company_name))
        connection.commit()
        cursor.close()
        flash("Account is created succesfully.", "success")
    except dbapi2.DatabaseError:
        flash("Account cannot createad.", "error")
        connection.rollback()
    finally:
        connection.close()
        return redirect(url_for('create_account'))


def set_prices(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        return render_template("set_prices.html", user_name=user_name, user_type=user_type)
    else:
        form_oiled = request.form["oiled"]
        form_dark = request.form["dark"]
        form_edged = request.form["edged"]
        form_light = request.form["light"]
        statement_HQ = """ UPDATE  PRICES SET OILED=%s, LIGHT=%s, DARK=%s, EDGED=%s WHERE(HQ_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))"""
        statement_BR = """ UPDATE  PRICES SET OILED=%s, LIGHT=%s, DARK=%s, EDGED=%s WHERE(BRANCH_ID = (SELECT ID FROM USERS WHERE (USERNAME = %s)))"""
        try:
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            if user_type == "branch":
                cursor.execute(statement_BR, (form_oiled,
                               form_light, form_dark, form_edged, user_name))
                connection.commit()
                cursor.close()
                flash("Prices have been set successfully.", "success")
            else:
                cursor.execute(statement_HQ, (form_oiled,
                               form_light, form_dark, form_edged, user_name))
                connection.commit()
                cursor.close()
                flash("Prices have been set successfully for each branch.", "success")
        except dbapi2.DatabaseError:
            flash("Prices cannot set.", "error")
            connection.rollback()
        finally:
            connection.close()
            return redirect(url_for('set_prices', user_name=user_name, user_type=user_type))


def change_password(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    if request.method == "GET":
        return render_template("change_password.html", user_name=user_name, user_type=user_type)
    else:
        form_conf_pass = request.form["confirm_pass"]
        form_new_pass = request.form["new_pass"]
        form_cur_pass = request.form["current_pass"]
        hashed_password = hasher.hash(form_new_pass)
        print(hashed_password)
        statement_1 = """ SELECT PASSWORD FROM USERS WHERE (USERNAME = %s)"""
        statement_2 = """ UPDATE USERS SET PASSWORD = %s WHERE(USERNAME = %s)"""
        if form_new_pass != form_conf_pass:
            flash("New and confirm passwords are not matching.", "error")
            return redirect(url_for('change_password', user_name=user_name, user_type=user_type))
    try:
        connection = dbapi2.connect(dsn)
        cursor = connection.cursor()
        cursor.execute(statement_1, (user_name,))
        prev_pass = cursor.fetchone()
        if (hasher.verify(form_cur_pass,prev_pass[0]) == False):
            flash("You entered your current password wrong.", "error")
            return redirect(url_for('change_password', user_name=user_name, user_type=user_type))
        cursor.execute(statement_2, (hashed_password, user_name))
        connection.commit()
        cursor.close()
        flash("Password is changed Succesfully.", "success")
    except dbapi2.DatabaseError:
        flash("Password connot changed.", "error")
        connection.rollback()
    finally:
        connection.close()
        return redirect(url_for('change_password', user_name=user_name, user_type=user_type))


def find_branch(user_type, user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    statement_1 = """SELECT FULL_NAME,COUNT(CUSTOMER_ID) , SUM(OILED_KG), SUM(DARK_KG), SUM(LIGHT_KG), SUM(EDGED_KG),
                     AVG(OILED_YIELD), AVG(DARK_YIELD), AVG(LIGHT_YIELD), AVG(EDGED_YIELD), USER_ID from
                     (select user_id, full_name from branches inner join relations on branches.user_id = relations.child_id
                     where relations.parent_ID = (SELECT ID FROM USERS WHERE USERNAME = %s) ) as a left join deposits on a.user_id = deposits.branch_id
                     group by full_name, USER_ID """
    try:
        connection = dbapi2.connect(dsn)
        cursor = connection.cursor()
        cursor.execute(statement_1, (user_name, ))
        branch_data = cursor.fetchall()
        connection.commit()
        cursor.close()   
    except dbapi2.DatabaseError:
        connection.rollback()
        flash("Customers cannot be fetched from database.","error")
    finally:
        connection.close()
        return render_template('find_branch.html',user_name = user_name, user_type = user_type, data = branch_data)

def see_reports(user_type,user_name):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    data = []
    if request.method == 'GET':        
        if user_type == 'HQ':
            statement_1 = """SELECT * FROM TRANSACTIONS INNER JOIN(
                           ( SELECT DEPOSITS.ID,B.FULL_NAME FROM DEPOSITS
                            INNER JOIN (SELECT A.CHILD_ID,CUSTOMERS.FULL_NAME FROM (SELECT CHILD_ID FROM RELATIONS WHERE PARENT_ID = 
							(SELECT ID FROM USERS WHERE USERNAME = %s) )
			                AS A INNER JOIN CUSTOMERS 
			                ON A.CHILD_ID = CUSTOMERS.USER_ID) AS B
                            ON DEPOSITS.CUSTOMER_ID = B.CHILD_ID  )  ) AS C ON TRANSACTIONS.DEPOSIT_ID = C.ID"""
        else:
            statement_1 = """SELECT * FROM TRANSACTIONS INNER JOIN(
                           ( SELECT DEPOSITS.ID,B.FULL_NAME FROM DEPOSITS
                            INNER JOIN (SELECT A.CHILD_ID,CUSTOMERS.FULL_NAME FROM (SELECT CHILD_ID FROM RELATIONS WHERE PARENT_ID = 
							(SELECT ID FROM USERS WHERE USERNAME = %s) )
			                AS A INNER JOIN CUSTOMERS 
			                ON A.CHILD_ID = CUSTOMERS.USER_ID) AS B
                            ON DEPOSITS.CUSTOMER_ID = B.CHILD_ID  )  ) AS C ON TRANSACTIONS.DEPOSIT_ID = C.ID"""
        try:
            connection = dbapi2.connect(dsn)
            cursor = connection.cursor()
            cursor.execute(statement_1, (user_name,))
            data.append(cursor.fetchall()) # data [0] : all transactions
            connection.commit()
            cursor.close()      
        except dbapi2.DatabaseError:
            flash("Data cannot fetched from database","error")
            connection.rollback()
        finally:
            connection.close()
            return render_template('see_reports.html', user_name = user_name, user_type = user_type,data= data)
    else:
            form_value = request.form["sort_value"]
            print("Value:")
            print(form_value)
            statement_1 = """(SELECT * FROM TRANSACTIONS INNER JOIN(
                           ( SELECT DEPOSITS.ID,B.FULL_NAME FROM DEPOSITS
                            INNER JOIN (SELECT A.CHILD_ID,CUSTOMERS.FULL_NAME FROM (SELECT CHILD_ID FROM RELATIONS WHERE PARENT_ID = 
							(SELECT ID FROM USERS WHERE USERNAME = %s) )
			                AS A INNER JOIN CUSTOMERS 
			                ON A.CHILD_ID = CUSTOMERS.USER_ID) AS B
                            ON DEPOSITS.CUSTOMER_ID = B.CHILD_ID  )  ) AS C ON TRANSACTIONS.DEPOSIT_ID = C.ID)
                            ORDER BY 
							case when (%s = 'full_name') THEN full_name end, 
							case when (%s = 'price') then price end,
							case when (%s = 'date') THEN date end  DESC                          
                            """
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (user_name,form_value,form_value,form_value))
                data.append(cursor.fetchall()) # data [0] : all transactions
                print(statement_1)
                connection.commit()
                cursor.close()
                flash("Sorted successfully","success")      
            except dbapi2.DatabaseError:
                flash("Data cannot fetched from database","error")
                connection.rollback()
            finally:
                connection.close()
                return render_template('see_reports.html', user_name = user_name, user_type = user_type,data= data)

def see_details(user_type,user_name,id):
    if 'username' in session:
        if session['username'] != user_name:
            return redirect(url_for('main_page'))
    else:
        return redirect(url_for('main_page'))
    data = []
    if request.method == 'GET':
        if user_type == 'branch':
            statement_1 = """ SELECT FULL_NAME FROM CUSTOMERS WHERE(USER_ID = %s) """
            statement_2 = """ SELECT * FROM TRANSACTIONS WHERE(DEPOSIT_ID = (SELECT ID FROM DEPOSITS WHERE (CUSTOMER_ID = %s)) )"""
            statement_3 = """ SELECT * FROM DEPOSITS WHERE (CUSTOMER_ID = %s) """
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (id,))
                data.append(cursor.fetchone()) # data[0][0] = name
                cursor.execute(statement_2, (id,))
                data.append(cursor.fetchall()) #data [1] transactions 
                cursor.execute(statement_3, (id,))
                data.append(cursor.fetchone()) # data[2] current deposits
                connection.commit()
                cursor.close()   
            except dbapi2.DatabaseError:
                flash("The data connot fetched from database.","error")
                connection.rollback()
            finally:
                connection.close()
                return render_template('see_details.html',user_name = user_name, user_type = user_type, id= id, data = data)
        else:
            statement_1 = """ SELECT FULL_NAME FROM BRANCHES WHERE(USER_ID = %s) """
            statement_2 = """ SELECT * FROM TRANSACTIONS WHERE(DEPOSIT_ID IN (SELECT ID FROM DEPOSITS WHERE (BRANCH_ID = %s)) )"""
            statement_3 = """ SELECT * FROM DEPOSITS WHERE (BRANCH_ID = %s) """
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                cursor.execute(statement_1, (id,))
                data.append(cursor.fetchone()) # data[0][0] = name
                cursor.execute(statement_2, (id,))
                data.append(cursor.fetchall()) #data [1] transactions 
                cursor.execute(statement_3, (id,))
                data.append(cursor.fetchone()) # data[2] current deposits
                connection.commit()
                cursor.close()   
            except dbapi2.DatabaseError:
                flash("The data connot fetched from database.","error")
                connection.rollback()
            finally:
                connection.close()
                return render_template('see_details.html',user_name = user_name, user_type = user_type, id= id, data = data)
    else:
        form_submit = request.form["submit"]
        if form_submit == 'edit':
            if user_type == 'branch':
                date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                form_oiled = int(request.form["oiled_kg"])
                form_dark = int(request.form["dark_kg"])
                form_light = int(request.form["light_kg"])
                form_edged = int(request.form["edged_kg"])
                statement_1 = """ INSERT INTO TRANSACTIONS (DEPOSIT_ID,DATE,PRICE,OILED,DARK,LIGHT,EDGED) VALUES ((SELECT ID FROM 
                            DEPOSITS WHERE ( CUSTOMER_ID = %s)),%s,-1,%s,%s,%s,%s) """
                statement_2 = """ UPDATE DEPOSITS SET OILED_KG = %s, DARK_KG = %s, LIGHT_KG = %s, EDGED_KG = %s
                            WHERE CUSTOMER_ID = %s"""
                try:
                    connection = dbapi2.connect(dsn)
                    cursor = connection.cursor()
                    cursor.execute(statement_1, (id,date,form_oiled,form_dark,form_light,form_edged))
                    print("A")
                    cursor.execute(statement_2, (form_oiled,form_dark,form_light,form_edged,id))
                    print("B")
                    connection.commit()
                    cursor.close()
                    flash("Customer is edited successfully.","success")
                except dbapi2.DatabaseError:
                    flash("The customer's data cannot edited.","error")
                    connection.rollback()
                finally:
                    connection.close()    
                    return redirect(url_for('see_details',user_name = user_name, user_type = user_type, id=id))
            else:
                form_name = request.form["full_name"]
                statement_1 = " UPDATE BRANCHES SET FULL_NAME = %s WHERE USER_ID = %s "
                statement_2 = " UPDATE USERS SET USERNAME = %s WHERE ID = %s"
                try:
                    connection = dbapi2.connect(dsn)
                    cursor = connection.cursor()
                    cursor.execute(statement_1, (form_name,id))
                    print("A")
                    cursor.execute(statement_2, (form_name,id))
                    print("B")
                    connection.commit()
                    cursor.close()
                    flash("Branch is edited.","success")
                except dbapi2.DatabaseError:
                    flash("The branches name cannot edited.","error")
                    connection.rollback()
                finally:
                    connection.close()    
                    return redirect(url_for('see_details',user_name = user_name, user_type = user_type, id=id))
        else:
            statement_1 = "DELETE FROM USERS WHERE ID = %s"
            try:
                connection = dbapi2.connect(dsn)
                cursor = connection.cursor()
                if user_type == 'HQ': # delete all customers of the branch
                    statement_2 = """ DELETE FROM USERS WHERE ID IN (SELECT CHILD_ID FROM RELATIONS WHERE PARENT_ID = %s) """
                    cursor.execute(statement_2, (id,))
                cursor.execute(statement_1, (id,))
                connection.commit()
                cursor.close()
                if user_type == 'branch':
                    flash("Customer is deleted successfully.","success")
                else:
                    flash("Branch is deleted successfully.","success")
            except dbapi2.DatabaseError:
                flash("The customer connot deleted from database.","error")
                connection.rollback()
            finally:
                connection.close()
                if user_type == 'branch':  
                    return redirect(url_for('find_customer',user_name = user_name, user_type = user_type))  
                else:
                     return redirect(url_for('find_branch',user_name = user_name, user_type = user_type))



app.add_url_rule("/", view_func=main_page, methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/dashboard", view_func=dashboard_page,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/add_customer", view_func=add_customer, methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/find_customer", view_func=find_customer, methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/add_branch", view_func=add_branch, methods=["GET", "POST"])
app.add_url_rule("/create_account", view_func=create_account,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/set_prices", view_func=set_prices,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/change_password", view_func=change_password,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/find_branch", view_func=find_branch,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/see_reports", view_func=see_reports,methods=["GET", "POST"])
app.add_url_rule("/<user_type>/<user_name>/see_details/<int:id>", view_func=see_details,methods=["GET", "POST"])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
