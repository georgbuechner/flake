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

function UpdateDates(date_string, surgery_start) {
  // Get all elements with `start_plus` (days to add/ days after surgery) attribute:
  var arr = document.querySelectorAll("[start_plus]");
  // Get current day and add surgery-start
  const day = new Date(date_string).getDate() + parseInt(surgery_start);
  // Iterate over all elements with `start_plus` attribute and modify date
  // accordings to start_plus 
  for (var i = 0; i < arr.length; i++) {
    const copiedDate = new Date(date_string);
    const start_plus = parseInt(arr[i].getAttribute("start_plus"))
    copiedDate.setDate(start_plus+parseInt(day));
    // Set date-value
    arr[i].setAttribute("value", copiedDate.toISOString().substring(0, 10));
  }
}

function GenerateP9(protocol) {
  alert("Funcionality not yet implemented. Sorry :(");
}

function GenerateScoreSheet(animal_id) {
  alert("Funcionality not yet implemented. Sorry :(");
}

function GenerateSurgerySheet(animal_id) {
  alert("Funcionality not yet implemented. Sorry :(");
}

function Store(animal_id) {
  alert("Funcionality not yet implemented. Sorry :(");
}
