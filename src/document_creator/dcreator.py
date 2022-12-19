import copy
import json
import os
import re
from docx import Document
from docx.shared import Cm
from typing import Dict, List, Tuple
from data_manager.dmanager import ExperimentData
from utils.dt_utils import strtodate, datetostr, datetostr_month, daterange, incdate

class DCreator:

    def __init__(
        self, 
        template_path: str, 
        protocol: str, 
        experiment_data: ExperimentData,
        animal_data: Dict[str, any],
        user_email
    ):
        # Load replacements
        with open("resources/replacements.json") as f:
            self.replacements = json.load(f)
        # Try to load protocol-specific template, otherwise use default.
        if os.path.exists(os.path.join(template_path, protocol)):
            self.doc = Document(os.path.join(template_path, f"{protocol}.docx"))
        else: 
            self.doc = Document(os.path.join(template_path, "default.docx"))
        # Data
        self.fields = experiment_data.dict()
        self.fields["general"].update(animal_data)
        self.fields["general"]["user-email"] = user_email

    def create_from_template(self):
        # Create document:
        self.__edit_paragraphs()
        self.__edit_tables()
        self.__edit_list_tables()
        # Save document:
        self.doc.save("src/output/surgery_sheet.docx")

    def create_score_sheet(self): 
        self.__edit_paragraphs()
        self.__edit_tables()
        user = self.fields["general"]["user"]
        start = strtodate(self.fields["general"]["start"]) 
        last_date = copy.deepcopy(start)
        weights = json.loads(self.fields["general"]["weights"])
        watercontrols = json.loads(self.fields["general"]["watercontrol"])
        monthly_weights = []
        data = {
            "data": {"weights": [], "watercontrol": [], "sig": []}, 
            "month_str": datetostr_month(last_date)
        }
        for i, w in enumerate(weights):
            data["data"]["weights"].append((last_date.day+1, f"{w:.1f}")) 
            data["data"]["watercontrol"].append((last_date.day+1, "W" if watercontrols[i] else "")) 
            data["data"]["sig"].append((last_date.day+1, "")) 
            cur_date = incdate(last_date, 1)
            if cur_date.month != last_date.month:
                monthly_weights.append(data)
                data = {
                    "data": {"weights": [], "watercontrol": [], "sig": []}, 
                    "month_str": datetostr_month(cur_date)
                }
            last_date = cur_date
        monthly_weights.append(data)
        def copy_table_after(table, paragraph):
            tbl, p = table._tbl, paragraph._p
            new_tbl = copy.deepcopy(tbl)
            p.addnext(new_tbl)
            self.doc.add_page_break()
        tbl = self.doc.tables[0]
        for x in range(len(monthly_weights)-1): 
            paragraph = self.doc.add_paragraph()
            copy_table_after(tbl, paragraph)
            
        def do_update(cell, data, cat): 
            print("Updating paragraph...")
            update_paragraph(cell.paragraphs[0], f"{{{x}}}", "")  # remove tag
            for i, val in data:
                print(f"  - {i}")
                if cat == "sig":
                    add_signiture(cell.paragraphs[0], user, 0.29)
                else:
                    update_paragraph(cell.paragraphs[0], "", val)

        remember_i = {}
        for i, month in enumerate(monthly_weights):
            table = self.doc.tables[i]
            table.rows[0].cells[0].paragraphs[0].text = month["month_str"]
            for x, data in month["data"].items():
                print(f"Month {i}, data: {x}")
                if x not in remember_i:
                    for r, row in enumerate(table.rows):
                        for c in range(2):
                            if f"{{{x}}}" in row.cells[c].paragraphs[0].text:
                                remember_i[x] = (r, c)
                                break
                if x in remember_i:
                    r, c = remember_i[x]
                    do_update(table.rows[r].cells[c], data, x)

        # Save document:
        self.doc.save("src/output/score_sheet.docx")

    ### replacing [tag]-s in paragraphs
    def __edit_paragraphs(self):
        """! Iterates over all paragraphs in search for tags """
        # Handle header
        header = self.doc.sections[0].header
        for par in header.paragraphs:
            par = self.__edit_paragraph(par, self.fields["general"])
        # Handle rest of document
        for par in self.doc.paragraphs:
            par = self.__edit_paragraph(par, self.fields["general"])

    ### replacing [tag]-s in tables
    def __edit_tables(self):
        """! Iterates over all tables in search for tags """
        for table in self.doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for par in cell.paragraphs:
                        par = self.__edit_paragraph(par, self.fields["general"])

    def __edit_paragraph(self, par, fields: Dict[str, List[Dict[str, any]]]):
        """! Edits paragraph by checking for tags and eventually replacing tag with entry. """
        result = re.search(r"\[(.*)\]", par.text)
        if result is not None:
            key = result.group(1)
            # Tag found
            if key in fields:
                update_paragraph(par, result.group(0), fields[key])
            # If signiture, add image 
            elif key == "signiture":
                update_paragraph(par, result.group(0), "")
                add_signiture(par, fields['user'], 2)
            # Empty (---) if tag not found.
            else:
                update_paragraph(par, result.group(0), "---")
        return par

    ### replacing <tag>-s in tables
    def __edit_list_tables(self):
        """! Iterates over tables in search for list-tags (adding rows per
        matching entry). 
        """
        def parse_value(value): 
            # Check for signal-word
            if isinstance(value, str):
                result = re.search(r"\{(.*)\}", value)
                if result is not None:
                    if result.group(1) in self.replacements:
                        return self.replacements[result.group(1)]
            # Convert datetime
            elif isinstance(value, datetime):
                return datetostr(entry)
            # Otherwise return value unchanged
            return value

        def get_iterator_and_source(par) -> Tuple[str, List[any]]:
            result = re.search(r"\{{(.*) in (.*)}}", par.text)
            if result is not None:
                update_paragraph(par, result.group(0), "")  # remove tag
                iterator_name = result.group(1)
                # range
                res = re.search(r"(.*)-(.*)", result.group(2))
                if res is not None:
                    start = self.fields["general"][res.group(1)]
                    end = self.fields["general"][res.group(2)]
                    return iterator_name, daterange(strtodate(start), strtodate(end))
                # conditional list (f.e. analgesic where name=Carprofen)...
                res = re.search(r"(.*) where (.*)==(.*)", result.group(2))
                if res is not None: #and res.group(1) in self.fields:
                    source = self.fields[res.group(1)]
                    filtered_source = [x for x in source if x[res.group(2)] == res.group(3)]
                    return iterator_name, filtered_source
                # list 
                if result.group(2) in self.fields:
                    return iterator_name, self.fields[result.group(2)]
            return None, None
                
        def get_tags(row) -> List[str]:
            tags = []
            for i in range(0, len(row.cells)):
                cell_par = row.cells[i].paragraphs[0]
                result = re.search(r"{(.*)}", cell_par.text)
                if result is not None:
                    update_paragraph(row.cells[i].paragraphs[0], result.group(0), "")
                    tags.append(result.group(1))
                else: 
                    print("Error in template: missing tag ({tag}) in table header")
            return tags

        def edit_table(table, tags: List[str], it: str, entry: any):
            # Add row to table with given information
            columns = table.add_row().cells
            for i, tag in enumerate(tags):
                if "." in tag: 
                    columns[i].text = parse_value(entry[tag.split(".")[1]])
                elif tag == it:
                    columns[i].text = parse_value(entry)
                elif tag in self.fields["general"]:
                    columns[i].text = parse_value(self.fields["general"][tag])
                elif re.search(r'“(.*)”', tag) is not None: 
                    columns[i].text = re.search(r'“(.*)”', tag).group(1)
                else:
                    print(f"For tag {tag} not found: {entry}!")

        # Iteratre over all tables in search for list-tags
        for table in self.doc.tables:
            # Get infos from first row
            row = table.rows[0]
            iterator, source_list = get_iterator_and_source(row.cells[0].paragraphs[0])
            if iterator is None: 
                continue 
            # Get tags
            tags = get_tags(row)
            # if command found, but no matching data, add "None-Row"
            if len(source_list) == 0:
                columns = table.add_row().cells
                for i in range(0, len(tags)):
                    columns[i].text = "---"
            # Otherwise, get tags and fill table.
            else:
                for entry in source_list:
                    edit_table(table, tags, iterator, entry)

def update_paragraph(par, old, new): 
    inline = par.runs 
    max_part = [0, 0]
    for i in range(len(inline)): 
        if old in inline[i].text: 
            text = inline[i].text.replace(old, new)
            inline[i].text = text
            return
    # If not found (since runs split old-text):
    par.text = par.text.replace(old, new)

def add_signiture(par, user: str, height: float):
    p = par.insert_paragraph_before("")
    r = p.add_run()
    if os.path.exists(f"data/signitures/{user}.png"):
        r.add_picture(f"data/signitures/{user}.png", height=Cm(height))
    else:
        r.add_picture(f"data/signitures/default.png", height=Cm(height))
