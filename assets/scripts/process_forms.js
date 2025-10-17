document.getElementById('web-form').addEventListener('submit', function(event) {
  event.preventDefault(); // Prevent form submission

  // Validate form inputs
  var name = document.getElementById('name').value.trim();
  var email = document.getElementById('email').value.trim();
  var formtype = document.getElementById('formtype').value.trim();

  if (document.getElementById('subject')) {
    var subject = document.getElementById('subject').value.trim();
  }
  if (document.getElementById('message')) {
    var message = document.getElementById('message').value.trim();
  }
  if (document.getElementById('mobile')) {
    var mobile = document.getElementById('mobile').value.trim();
  }
  if (document.getElementById('genre')) {
    var genre = document.getElementById('genre').value.trim();
  }
  if (document.getElementById('url')) {
    var url = document.getElementById('url').value.trim();
  }
  
  // Email validation using a regular expression
  var emailRegex = /^\S+@\S+\.\S+$/;
 
  // Construct the form data 

  if ( formtype == "contact") {
    if (!name || !email || !subject || !message || !emailRegex.test(email)) {
      alert('Please fill in all fields with valid inputs.');
      return;
    }
    var formData = {
      formtype: formtype,
      name: name,
      email: email,
      subject: subject,
      message: message
    };
  } else if ( formtype == "preregistration") {
    if (!name || !email || !mobile || !message || !emailRegex.test(email) || !url) {
      alert('Please fill in all fields with valid inputs.');
      return;
    }
    var formData = {
      formtype: formtype,
      name: name,
      email: email,
      mobile: mobile,
      message: message,
      url: url
    };
  }  else if ( formtype == "subscribe") {
    if ( !email || !emailRegex.test(email)) {
      alert('Please fill in all fields with valid inputs.');
      return;
    }
    var formData = {
      formtype: formtype,
      name: name,
      email: email
    };
  }

  // Perform form submission
  submitForm(formData);
});

function submitForm(formData) {
  // Make an API request to the backend (API Gateway) for form submission
  fetch('https://l21kpppyx6.execute-api.ap-southeast-2.amazonaws.com/main/submit', { // URL that represents the backend API endpoint to which the form data is going to be sent
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(formData)
  })
  .then(function(response) {
    if (response.ok && formData.formtype == "preregistration") {
      // Redirect to the thank you page
      window.location.href = 'thank-you-prereg.html';
    } else if (response.ok) {
      // Redirect to the thank you page
      window.location.href = 'thank-you.html';
    } else {
      throw new Error('Form submission failed.');
    }
  })
  .catch(function(error) {
    console.error(error);
    alert('Form submission failed. Please try again later.');
  });
}
