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

async function Del(category, name) {
  const escaped_name = escape(name).replace("/", "_");
  console.log(category, escaped_name);
  try {
    // Send request:
    let r = await fetch("/definitions/delete/"+category+"/"+escaped_name, {
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

