async function UploadSignature(escaped_user) {
  const elem = document.getElementById("signature");
  if (elem.files.length == 0) {
    alert("No file selected!");
    return;
  }
  let signature_file = elem.files[0];
  console.log(signature_file);
  let formData = new FormData();

  formData.append("sig", signature_file);
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  // Send request to server.
  try {
    // Send request:
    let r = await fetch('/upload/signature/'+escaped_user, 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    // Handle response:
    if (r.ok) {
      if (r.status === 206) {
        let response_text = await r.text()
        alert(response_text);
      }
      window.location=window.location;
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

async function DeleteSignature(escaped_user) {
  try {
    // Send request:
    let r = await fetch("/delete/signature/"+escaped_user, {method: "POST", body: new FormData}); 
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
