async function UploadPyratData(user) 
{
  let user_infos = { "name": user.replace(" ", "-").toLowerCase()};
  let pyrat_csv = document.getElementById("pyrat_csv").files[0];
  console.log(pyrat_csv)
  let formData = new FormData();

  formData.append("csv", pyrat_csv);
  formData.append("user", JSON.stringify(user_infos));
  
  const ctrl = new AbortController()    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  try {
   let r = await fetch('/upload/pyrat_csv', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200) {
      window.location=window.location
    }
    else {
      alert("Something went wrong: Error code: " + r.status)
    }
  } catch(e) {
    console.log('Huston we have problem...:' + e);
    alert("Something went wrong: " + e)
  }
}
