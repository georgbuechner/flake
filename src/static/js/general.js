async function UploadPyratData(user) 
{
  let user_infos = { "name": user.replace(" ", "-").toLowerCase()};
  let pyrat_csv = document.getElementById("pyrat_csv").files[0];
  console.log(pyrat_csv);
  let formData = new FormData();

  formData.append("csv", pyrat_csv);
  formData.append("user", JSON.stringify(user_infos));
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  try {
   let r = await fetch('/upload/pyrat_csv', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200) {
      window.location=window.location;
    }
    if (r.status === 409) {
      alert("Animal with this id already exists!");
    }
    else {
      alert("Something went wrong: Error code: " + r.status);
    }
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

function UpdateDates(date_string, surgery_start) {
  // Get all elements with `start_plus` (days to add/ days after surgery) attribute:
  var arr = document.querySelectorAll("[start_plus]");
  // Get current day and add surgery-start
  const day = new Date(date_string).getDate() + parseInt(surgery_start);
  // Iterate over all elements with `start_plus` attribute and modify date
  // accordings to start_plus 
  max_date = 0;
  for (var i = 0; i < arr.length; i++) {
    // Create copy and increment days by `start_plus` value of elemenyt
    const copiedDate = new Date(date_string);
    const start_plus = parseInt(arr[i].getAttribute("start_plus"));
    copiedDate.setDate(start_plus+parseInt(day));
    // Set date-value
    arr[i].setAttribute("value", copiedDate.toISOString().substring(0, 10));
    // Check if new date might by new max-date
    if (copiedDate.getTime() > max_date)
      max_date = copiedDate.getTime()
  }
  // Set end-date
  const endDate = new Date(max_date);
  let end_date_elem = document.getElementById("end");
  end_date_elem.setAttribute("value", endDate.toISOString().substring(0, 10));
  // Send message to user to double check all entries.
  alert("All dates have been auto filled based on protocol-specific information. You should double-check!");
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
