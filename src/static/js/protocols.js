function AddProtocol(entry) { 
  var dialog = document.getElementById("add_protocol_modal"); 
  dialog.showModal();
} 

function Close(modal_name) { 
  var dialog = document.getElementById(modal_name); 
  dialog.close();
}

async function DelSub(protocol, subprotocol) {
  let params = protocol 
  if (subprotocol != "") 
    params +="/" + subprotocol;
  console.log(protocol, subprotocol, params);
  try {
    // Send request:
    let r = await fetch("/settings/protocols/remove/" + params, {
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
