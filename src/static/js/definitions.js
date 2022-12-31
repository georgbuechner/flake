function Add(entry) { 
  // Fill entries with current entries:
  console.log(entry);
  if (entry !== undefined) {
    for (var i=0; i<entry.children.length; i++) {
      if (entry.children[i].hasAttribute("name")) {
        var elem = document.getElementById(entry.children[i].getAttribute("name"));
        if (elem.type == "checkbox")
          elem.checked = entry.children[i].innerHTML === "True";
        else 
          elem.value=entry.children[i].innerHTML;
      }
    }
  }
  // open add-/edit-modal
  var dialog = document.getElementById("edit_modal"); 
  console.log("SHOW!!");
  dialog.showModal();
} 

async function Del(category, name, full_protocol) {
  const escaped_name = escape(name).replace("/", "_");
  let base_url = ""
  if (full_protocol !== undefined) 
    base_url = "/settings/protocols/" + full_protocol
  else 
    base_url = "/definitions"
  console.log(category, escaped_name);
  try {
    // Send request:
    let r = await fetch(base_url+"/delete/"+category+"/"+escaped_name, {
      method: "POST", body: new FormData}); 
    // Handle response:
    if (r.status === 200)
      window.location=window.location;
    else 
      alert("Unkown error. Sorry " + r.status);
  } catch(e) {
    console.log(e);
    alert("Unkown error. Sorry", e);
  }
}

function CloseModal() { 
  var dialog = document.getElementById("edit_modal"); 
  dialog.close(); 
}

function Set(elem) {
  console.log("all definitions: ", definitions)
  const getByKey = (arr, key) => (arr.find(x => x["name"] === key) || {});
  const definition = getByKey(definitions, elem.value);
  for (const [key, value] of Object.entries(definition)) {
    let el = document.getElementById(key)
    if ((el || {}).type === "checkbox" && value === true)
      el.checked = true;
    else if ((el || {}).type === "checkbox" && value === false)
      el.checked = false;
    else 
      el.value = value; 
  }
}
