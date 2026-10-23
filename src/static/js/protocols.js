function AddProtocol(entry) { 
  var dialog = document.getElementById("add_protocol_modal"); 
  dialog.showModal();
} 

function DeleteProtocol(protocol) { 
  document.getElementById('delete_protocol_btn').setAttribute("onclick",
    "DelSub('" + protocol +"', '')");
  var dialog = document.getElementById("confirm_modal"); 
  dialog.showModal();
} 

function DeleteSubprotocol(protocol, subprotocol) { 
  document.getElementById('delete_protocol_btn').setAttribute("onclick",
    "DelSub('" + protocol +"', '" + subprotocol + "')");
  var dialog = document.getElementById("confirm_modal"); 
  dialog.showModal();
}

function Close(modal_name) { 
  var dialog = document.getElementById(modal_name); 
  dialog.close();
}

async function DelSub(protocol, subprotocol) {
  let params = protocol 
  if (subprotocol != "") {
    // Check for corrupted subprotocols (if they include the protocal again)
    // In that case, replace the "/" by "_" so that the path is correct
    // (protocol/subprotocol and not protocol/protocol/subprotocol) but the
    // original can still be found (instead of f.e. removing the protocol from
    // the subprotocol)
    if (subprotocol.includes("/"))
      subprotocol = subprotocol.replace("/", "_")
    params +="/" + subprotocol;
  }
  console.log(protocol, subprotocol, params);
  // Send request:
  let reload = false;
  try {
    const response = await AppFetch(
      "/settings/protocols/remove/" + params, 
      {method: "POST", body: new FormData}
    );
    if (response.ok) {
      reload = true;
    } else {
      const message = await response.text();
      OpenErrorModal(message, response.status);
    }
  } catch(error) {
    console.error("Failed deleting protocol or subprotocol:", error);
    OpenErrorModal();
  }
  if (reload) {
    window.location.reload();
  }
}
